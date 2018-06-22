# -*- coding: utf-8 -*-
'''
Common tests for IOs:
 * check presence of all necessary attr
 * check types
 * write/read consistency

See BaseTestIO.


The public URL is in url_for_tests.

To deposite new testing files,  please create a account at
gin.g-node.org and upload files at NeuralEnsemble/ephy_testing_data
data repo.

'''

# needed for python 3 compatibility
from __future__ import absolute_import

__test__ = False

# url_for_tests = "https://portal.g-node.org/neo/" #This is the old place
url_for_tests = "https://web.gin.g-node.org/NeuralEnsemble/ephy_testing_data/raw/master/"

import os
from copy import copy

try:
    import unittest2 as unittest
except ImportError:
    import unittest

from neo.core import Block, Segment
from neo.test.tools import (assert_same_sub_schema,
                            assert_neo_object_is_compliant,
                            assert_sub_schema_is_lazy_loaded,
                            assert_lazy_sub_schema_can_be_loaded,
                            assert_children_empty)

from neo.rawio.tests.tools import (can_use_network, make_all_directories,
                                   download_test_file, create_local_temp_dir)

from neo.test.iotest.tools import (cleanup_test_file,
                                   close_object_safe, create_generic_io_object,
                                   create_generic_reader,
                                   create_generic_writer,
                                   iter_generic_io_objects,
                                   iter_generic_readers, iter_read_objects,
                                   read_generic,
                                   write_generic)
from neo.test.generate_datasets import generate_from_supported_objects


class BaseTestIO(object):
    '''
    This class make common tests for all IOs.

    Several startegies:
      * for IO able to read write : test_write_then_read
      * for IO able to read write with hash conservation (optional):
        test_read_then_write
      * for all IOs : test_assert_readed_neo_object_is_compliant
        2 cases:
          * files are at G-node and downloaded:
            download_test_files_if_not_present
          * files are generated by MyIO.write()

    '''
    # ~ __test__ = False

    # all IO test need to modify this:
    ioclass = None  # the IOclass to be tested

    files_to_test = []  # list of files to test compliances
    files_to_download = []  # when files are at G-Node

    # when reading then writing produces files with identical hashes
    hash_conserved_when_write_read = False
    # when writing then reading creates an identical neo object
    read_and_write_is_bijective = True

    # allow environment to tell avoid using network
    use_network = can_use_network()

    local_test_dir = None

    def setUp(self):
        '''
        Set up the test fixture.  This is run for every test
        '''
        self.files_to_test = copy(self.__class__.files_to_test)
        self.higher = self.ioclass.supported_objects[0]
        self.shortname = self.ioclass.__name__.lower().rstrip('io')
        # these objects can both be written and read
        self.io_readandwrite = list(set(self.ioclass.readable_objects) &
                                    set(self.ioclass.writeable_objects))
        # these objects can be either written or read
        self.io_readorwrite = list(set(self.ioclass.readable_objects) |
                                   set(self.ioclass.writeable_objects))
        self.create_local_dir_if_not_exists()
        self.download_test_files_if_not_present()
        self.files_generated = []
        self.generate_files_for_io_able_to_write()
        self.files_to_test.extend(self.files_generated)

    def create_local_dir_if_not_exists(self):
        '''
        Create a local directory to store testing files and return it.

        The directory path is also written to self.local_test_dir
        '''
        self.local_test_dir = create_local_temp_dir(
            self.shortname, directory=os.environ.get("NEO_TEST_FILE_DIR", None))
        return self.local_test_dir

    def download_test_files_if_not_present(self):
        '''
        Download %s file at G-node for testing
        url_for_tests is global at beginning of this file.

        ''' % self.ioclass.__name__
        if not self.use_network:
            raise unittest.SkipTest("Requires download of data from the web")

        url = url_for_tests + self.shortname
        try:
            make_all_directories(self.files_to_download, self.local_test_dir)
            download_test_file(self.files_to_download,
                               self.local_test_dir, url)
        except IOError as exc:
            raise unittest.TestCase.failureException(exc)

    download_test_files_if_not_present.__test__ = False

    def cleanup_file(self, path):
        '''
        Remove test files or directories safely.
        '''
        cleanup_test_file(self.ioclass, path, directory=self.local_test_dir)

    def able_to_write_or_read(self, writeread=False, readwrite=False):
        '''
        Return True if generalized writing or reading is possible.

        If writeread=True, return True if writing then reading is
        possible and produces identical neo objects.

        If readwrite=True, return True if reading then writing is possible
        and produces files with identical hashes.
        '''
        # Find the highest object that is supported by the IO
        # Test only if it is a Block or Segment, and if it can both read
        # and write this object.
        if self.higher not in self.io_readandwrite:
            return False
        if self.higher not in [Block, Segment]:
            return False

        # when io need external knowldge for writting or read such as
        # sampling_rate (RawBinaryIO...) the test is too much complex to design
        # genericaly.
        if (self.higher in self.ioclass.read_params and
                    len(self.ioclass.read_params[self.higher]) != 0):
            return False

        # handle cases where the test should write then read
        if writeread and not self.read_and_write_is_bijective:
            return False

        # handle cases where the test should read then write
        if readwrite and not self.hash_conserved_when_write_read:
            return False

        return True

    def get_filename_path(self, filename):
        '''
        Get the path to a filename in the current temporary file directory
        '''
        return os.path.join(self.local_test_dir, filename)

    def generic_io_object(self, filename=None, return_path=False, clean=False):
        '''
        Create an io object in a generic way that can work with both
        file-based and directory-based io objects.

        If filename is None, create a filename (default).

        If return_path is True, return the full path of the file along with
        the io object.  return ioobj, path.  Default is False.

        If clean is True, try to delete existing versions of the file
        before creating the io object.  Default is False.
        '''
        return create_generic_io_object(ioclass=self.ioclass,
                                        filename=filename,
                                        directory=self.local_test_dir,
                                        return_path=return_path,
                                        clean=clean)

    def create_file_reader(self, filename=None, return_path=False,
                           clean=False, target=None, readall=False):
        '''
        Create a function that can read from the specified filename.

        If filename is None, create a filename (default).

        If return_path is True, return the full path of the file along with
        the reader function.  return reader, path.  Default is False.

        If clean is True, try to delete existing versions of the file
        before creating the io object.  Default is False.

        If target is None, use the first supported_objects from ioobj
        If target is False, use the 'read' method.
        If target is the Block or Segment class, use read_block or
        read_segment, respectively.
        If target is a string, use 'read_'+target.

        If readall is True, use the read_all_ method instead of the read_
        method. Default is False.
        '''
        ioobj, path = self.generic_io_object(filename=filename,
                                             return_path=True, clean=clean)

        res = create_generic_reader(ioobj, target=target, readall=readall)

        if return_path:
            return res, path
        return res

    def create_file_writer(self, filename=None, return_path=False,
                           clean=False, target=None):
        '''
        Create a function that can write from the specified filename.

        If filename is None, create a filename (default).

        If return_path is True, return the full path of the file along with
        the writer function.  return writer, path.  Default is False.

        If clean is True, try to delete existing versions of the file
        before creating the io object.  Default is False.

        If target is None, use the first supported_objects from ioobj
        If target is False, use the 'write' method.
        If target is the Block or Segment class, use write_block or
        write_segment, respectively.
        If target is a string, use 'write_'+target.
        '''
        ioobj, path = self.generic_io_object(filename=filename,
                                             return_path=True, clean=clean)

        res = create_generic_writer(ioobj, target=target)

        if return_path:
            return res, path
        return res

    def read_file(self, filename=None, return_path=False, clean=False,
                  target=None, readall=False, lazy=False):
        '''
        Read from the specified filename.

        If filename is None, create a filename (default).

        If return_path is True, return the full path of the file along with
        the object.  return obj, path.  Default is False.

        If clean is True, try to delete existing versions of the file
        before creating the io object.  Default is False.

        If target is None, use the first supported_objects from ioobj
        If target is False, use the 'read' method.
        If target is the Block or Segment class, use read_block or
        read_segment, respectively.
        If target is a string, use 'read_'+target.

        The lazy parameter is passed to the reader.  Defaults is True.

        If readall is True, use the read_all_ method instead of the read_
        method. Default is False.
        '''
        ioobj, path = self.generic_io_object(filename=filename,
                                             return_path=True, clean=clean)
        obj = read_generic(ioobj, target=target, lazy=lazy,
                           readall=readall, return_reader=False)

        if return_path:
            return obj, path
        return obj

    def write_file(self, obj=None, filename=None, return_path=False,
                   clean=False, target=None):
        '''
        Write the target object to a file using the given neo io object ioobj.

        If filename is None, create a filename (default).

        If return_path is True, return the full path of the file along with
        the object.  return obj, path.  Default is False.

        If clean is True, try to delete existing versions of the file
        before creating the io object.  Default is False.

        If target is None, use the first supported_objects from ioobj
        If target is False, use the 'read' method.
        If target is the Block or Segment class, use read_block or
        read_segment, respectively.
        If target is a string, use 'read_'+target.

        obj is the object to write.  If obj is None, an object is created
        automatically for the io class.
        '''
        ioobj, path = self.generic_io_object(filename=filename,
                                             return_path=True, clean=clean)
        obj = write_generic(ioobj, target=target, return_reader=False)

        if return_path:
            return obj, path
        return obj

    def iter_io_objects(self, return_path=False, clean=False):
        '''
        Return an iterable over the io objects created from files_to_test

        If return_path is True, yield the full path of the file along with
        the io object.  yield ioobj, path  Default is False.

        If clean is True, try to delete existing versions of the file
        before creating the io object.  Default is False.
        '''
        return iter_generic_io_objects(ioclass=self.ioclass,
                                       filenames=self.files_to_test,
                                       directory=self.local_test_dir,
                                       return_path=return_path,
                                       clean=clean)

    def iter_readers(self, target=None, readall=False,
                     return_path=False, return_ioobj=False, clean=False):
        '''
        Return an iterable over readers created from files_to_test.

        If return_path is True, return the full path of the file along with
        the reader object.  return reader, path.

        If return_ioobj is True, return the io object as well as the reader.
        return reader, ioobj.  Default is False.

        If both return_path and return_ioobj is True,
        return reader, path, ioobj.  Default is False.

        If clean is True, try to delete existing versions of the file
        before creating the io object.  Default is False.

        If readall is True, use the read_all_ method instead of the
        read_ method. Default is False.
        '''
        return iter_generic_readers(ioclass=self.ioclass,
                                    filenames=self.files_to_test,
                                    directory=self.local_test_dir,
                                    return_path=return_path,
                                    return_ioobj=return_ioobj,
                                    target=target,
                                    clean=clean,
                                    readall=readall)

    def iter_objects(self, target=None, return_path=False, return_ioobj=False,
                     return_reader=False, clean=False, readall=False,
                     lazy=False):
        '''
        Iterate over objects read from the list of filenames in files_to_test.

        If target is None, use the first supported_objects from ioobj
        If target is False, use the 'read' method.
        If target is the Block or Segment class, use read_block or
        read_segment, respectively.
        If target is a string, use 'read_'+target.

        If return_path is True, yield the full path of the file along with
        the object.  yield obj, path.

        If return_ioobj is True, yield the io object as well as the object.
        yield obj, ioobj.  Default is False.

        If return_reader is True, yield the io reader function as well as the
        object. yield obj, reader.  Default is False.

        If some combination of return_path, return_ioobj, and return_reader
        is True, they are yielded in the order: obj, path, ioobj, reader.

        If clean is True, try to delete existing versions of the file
        before creating the io object.  Default is False.

        The lazy parameters is passed to the reader.  Defaults is True.

        If readall is True, use the read_all_ method instead of the read_
        method. Default is False.
        '''
        return iter_read_objects(ioclass=self.ioclass,
                                 filenames=self.files_to_test,
                                 directory=self.local_test_dir,
                                 target=target,
                                 return_path=return_path,
                                 return_ioobj=return_ioobj,
                                 return_reader=return_reader,
                                 clean=clean, readall=readall,
                                 lazy=lazy)

    def generate_files_for_io_able_to_write(self):
        '''
        Write files for use in testing.
        '''
        self.files_generated = []
        if not self.able_to_write_or_read():
            return

        generate_from_supported_objects(self.ioclass.supported_objects)

        ioobj, path = self.generic_io_object(return_path=True, clean=True)
        if ioobj is None:
            return

        self.files_generated.append(path)

        write_generic(ioobj, target=self.higher)

        close_object_safe(ioobj)

    def test_write_then_read(self):
        '''
        Test for IO that are able to write and read - here %s:
          1 - Generate a full schema with supported objects.
          2 - Write to a file
          3 - Read from the file
          4 - Check the hierachy
          5 - Check data

        Work only for IO for Block and Segment for the highest object
        (main cases).
        ''' % self.ioclass.__name__

        if not self.able_to_write_or_read(writeread=True):
            return

        ioobj1 = self.generic_io_object(clean=True)

        if ioobj1 is None:
            return

        ob1 = write_generic(ioobj1, target=self.higher)
        close_object_safe(ioobj1)

        ioobj2 = self.generic_io_object()

        # Read the highest supported object from the file
        obj_reader = create_generic_reader(ioobj2, target=False)
        ob2 = obj_reader()[0]
        if self.higher == Segment:
            ob2 = ob2.segments[0]

        # some formats (e.g. elphy) do not support double floating
        # point spiketrains
        try:
            assert_same_sub_schema(ob1, ob2, True, 1e-8)
            assert_neo_object_is_compliant(ob1)
            assert_neo_object_is_compliant(ob2)
        # intercept exceptions and add more information
        except BaseException as exc:
            raise

        close_object_safe(ioobj2)

    def test_read_then_write(self):
        '''
        Test for IO that are able to read and write, here %s:
         1 - Read a file
         2 Write object set in another file
         3 Compare the 2 files hash

        NOTE: TODO: Not implemented yet
        ''' % self.ioclass.__name__

        if not self.able_to_write_or_read(readwrite=True):
            return
            # assert_file_contents_equal(a, b)

    def test_assert_readed_neo_object_is_compliant(self):
        '''
        Reading %s files in `files_to_test` produces compliant objects.

        Compliance test: neo.test.tools.assert_neo_object_is_compliant for
        lazy mode.
        ''' % self.ioclass.__name__
        # This is for files presents at G-Node or generated
        lazy_list = [False]
        if self.ioclass.support_lazy:
            lazy_list.append(True)

        for lazy in lazy_list:
            for obj, path in self.iter_objects(lazy=lazy, return_path=True):
                try:
                    # Check compliance of the block
                    assert_neo_object_is_compliant(obj)
                # intercept exceptions and add more information
                except BaseException as exc:
                    exc.args += ('from %s with lazy=%s' %
                                 (os.path.basename(path), lazy),)
                    raise

    def test_readed_with_lazy_is_compliant(self):
        '''
        Reading %s files in `files_to_test` with `lazy` is compliant.

        Test the reader with lazy = True.  All objects derived from ndarray
        or Quantity should have a size of 0. Also, AnalogSignal,
        AnalogSignalArray, SpikeTrain, Epoch, and Event should
        contain the lazy_shape attribute.
        ''' % self.ioclass.__name__
        # This is for files presents at G-Node or generated
        if self.ioclass.support_lazy:
            for obj, path in self.iter_objects(lazy=True, return_path=True):
                try:
                    assert_sub_schema_is_lazy_loaded(obj)
                # intercept exceptions and add more information
                except BaseException as exc:
                    raise

    def test_load_lazy_objects(self):
        '''
        Reading %s files in `files_to_test` with `lazy` works.

        Test the reader with lazy = True.  All objects derived from ndarray
        or Quantity should have a size of 0. Also, AnalogSignal,
        AnalogSignalArray, SpikeTrain, Epoch, and Event should
        contain the lazy_shape attribute.
        ''' % self.ioclass.__name__
        if not hasattr(self.ioclass, 'load_lazy_object'):
            return

        # This is for files presents at G-Node or generated
        for obj, path, ioobj in self.iter_objects(
                lazy=True,
                return_ioobj=True,
                return_path=True):
            try:
                assert_lazy_sub_schema_can_be_loaded(obj, ioobj)
            # intercept exceptions and add more information
            except BaseException as exc:
                raise
