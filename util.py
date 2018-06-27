"""
This module contains functions that I don't know where to put.
"""
import os

import h5py
import numpy as np
from numba import jit, int64


##################################################################
#
#       Parse the list of data files
#
##################################################################

def parse_data_list(txt_file, file_type="h5"):
    """
    Provide an interface to parse the data list.

    :param txt_file: The txt file containing the list of all data files.
    :param file_type: The type of data files
    :return: A dictionary in the following format.

            {"Files":[A list of all names in the txt file] ,
             Name_1:{Datasets:[a list of datsets to process],
                     data_num:[a list of data number in each data set]}
             ...

             }

    """

    available_file_type = ["h5", ]

    if file_type == "h5":
        return _parse_h5_data_list(txt_file)
    else:
        raise Exception("Invalid value for file_type. Currently, available file types are: ",
                        available_file_type)


def _parse_h5_data_list(txt_file):
    """
    Exam each h5 files listed in the txt_file. It returns a dictionary contains the addresses to each
    h5 files and the datasets to process and the pattern number of each data sets.
    It also checks the shape of each data set.

    Notice that, the order of the file is strictly the order given by the user. If the user
    has specified the order the dataset, then the order of the dataset is strictly that specified by the user.
    If the user has not specified the order of the dataset. The it's ordered according to lexicographical order.
    i.e.

    keys = list(file.keys())
    keys = keys.sort(key = str.lower)

    This also means, your dataset name can only use ASCII characters.

    :param txt_file: The txt file containing the list to parse.
    :return: a dictionary containing the necessary information.
    """

    dict_holder = {"Files": []}

    # Read the lines. Do not change the order of the files in the txt file.
    with open(txt_file, 'r') as txtFile:
        lines = txtFile.readlines()

    # Remove redundant "/n" symbol and blank spaces
    lines = [x.strip('\n') for x in lines]
    lines = [x.strip() for x in lines]

    """
    This parser exams Three times through the file.
    The first loop, create entries for each h5 file. 
    The second loop, exams whether the user has specified data sets to process.
    The third loop, exam each data set to check for pattern number and pattern shape.
    """

    # Record the line number for each line beginning with "File:"
    file_pos = []

    """
    First loop, check for existence
    """
    for num in range(len(lines)):
        line = lines[num]

        # If the first 5 characters are "File:", then append
        # the address to the corresponding file to dict_holder["Files"]
        if line[:5] == "File:":

            address = line[5:]
            # Check if the file exists and is intact
            try:
                with h5py.File(address, 'r'):
                    pass

                # Because the file exist, append the file address to dict_holder["Files"]
                dict_holder["Files"].append(address)

                # Create entries for this h5 file.
                dict_holder.update({address: {"Datasets": [],
                                              "data_num": []}})

                # Record the line number of this file
                file_pos.append(num)

            except IOError:
                raise Exception("The file {} does not exit or is damaged.".format(address) +
                                "Please make sure all the data source h5 files are intact" +
                                "before launching this program.")

    file_list = dict_holder["Files"]
    # Check if all the files are different. Because I am using the absolute path, this can be done easily
    if len(set(file_list)) != len(file_list):
        raise Exception("There are duplicated h5 files specified in the list." +
                        "Please make sure that all the h5 files listed in {} ".format(txt_file) +
                        "are unique.")

    """
    Second loop, check for user specified data sets
    """
    file_num_total = len(file_list)
    file_pos.append(len(lines))  # To specify the range of lines to search, for the last file in the list.

    # First check all the other files except the last one.
    for file_idx in range(file_num_total):
        # Check lines between this file and the next file
        """
        The default behavior is to process all data sets in the h5 file. 
        If the user specify a data set, then set this flag to 0. In this case,
        only process those data sets specified by the user.
        """
        default_flag = 1
        for line_idx in range(file_pos[file_idx], file_pos[file_idx + 1]):

            line = lines[line_idx]
            # Check if this line begins with "Dataset:"
            if line[:8] == "Dataset:":
                # If user specifies data sets, set this flag to zero to disable the default behavior.
                default_flag = 0
                dict_holder[file_list[file_idx]]["Datasets"].append(line[8:])

        # If it's to use default behavior.
        if default_flag == 1:
            with h5py.File(file_list[file_idx], 'r') as h5file:
                keys = list(h5file.keys())
                # Make sure the keys are in lexicographical order
                dict_holder[file_list[file_idx]]["Datasets"] = keys

    """
    Third loop, check for data number and data shape
    """

    # Get a shape
    with h5py.File(file_list[0], 'r') as h5file:
        key = dict_holder[file_list[0]]["Datasets"][0]
        data_set = h5file[key]
        dict_holder.update({"shape": data_set.shape[1:]})

    for file_address in file_list:

        with h5py.File(file_address, 'r') as h5file:
            for key in dict_holder[file_address]["Datasets"]:
                data_set = h5file[key]
                dict_holder[file_address]["data_num"].append(data_set.shape[0])
                # Check if the data size is correct
                if dict_holder["shape"] != data_set.shape[1:]:
                    raise Exception("The shape of the dataset {}".format(key) +
                                    "in file {}".format(file_address) +
                                    "is different from the intended shape." +
                                    "Please check if the shape of all samples are the same.")

    # Return the result
    return dict_holder


##################################################################
#
#       Get batch number list
#
##################################################################

def get_batch_num_list(total_num, batch_num):
    """
    Generate a list containing the data number per batch.
    The idea is that the difference between each batches is at most one pattern.

    :param total_num: The total number of patterns.
    :param batch_num: The number of batches to build.
    :return: A list containing the data number in each batch.
    """

    redundant_num = np.mod(total_num, batch_num)
    if redundant_num != 0:
        number_per_batch = total_num // batch_num
        batch_num_list = [number_per_batch + 1, ] * redundant_num
        batch_num_list += [number_per_batch, ] * (batch_num - redundant_num)
    else:
        number_per_batch = total_num // batch_num
        batch_num_list = [number_per_batch, ] * batch_num

    return batch_num_list


##################################################################
#
#       Get global index map
#
##################################################################

def get_global_index_map(data_num_total,
                         file_num,
                         data_num_per_file,
                         dataset_num_per_file,
                         data_num_per_dataset):
    """
    Return an array containing the map from the global index to file index, dataset index and the local
    index for the specific pattern.

    :param data_num_total: The total number of data points.
    :param file_num: The number of files.
    :param data_num_per_file: The data point number in each file
    :param dataset_num_per_file: The dataset number in each file
    :param data_num_per_dataset: The data point number in each dataset.
    :return: A numpy array containing the map
                           [
     global index -->       [file index, dataset index, local index]],
                            [file index, dataset index, local index]],
                            [file index, dataset index, local index]],
                                    ....
                           ]

    """
    holder = np.zeros((3, data_num_total), dtype=np.int64)
    # Starting point of the global index for different files
    global_idx_file_start = 0
    for file_idx in range(file_num):
        # End point of the global index for different files
        global_idx_file_end = global_idx_file_start + data_num_per_file[file_idx]
        # Assign file index
        holder[0, global_idx_file_start: global_idx_file_end] = file_idx
        """
        Postpone the update of the starting point until the end of the loop.
        """

        # Process the dataset index
        # Starting point of the global index for different dataset
        global_idx_dataset_start = global_idx_file_start
        for dataset_idx in range(dataset_num_per_file[file_idx]):
            # End point of the global index for different dataset
            global_idx_dataset_end = global_idx_dataset_start + data_num_per_dataset[file_idx][dataset_idx]
            # Assign the dataset index
            holder[1, global_idx_dataset_start: global_idx_dataset_end] = dataset_idx
            # Assign the local index within each dataset
            holder[2, global_idx_dataset_start:global_idx_dataset_end] = np.arange(
                data_num_per_dataset[file_idx][dataset_idx])

            # Update the starting global index of the dataset
            global_idx_dataset_start = global_idx_dataset_end

        # update the start point for the global index of the file
        global_idx_file_start = global_idx_file_end

    return holder


##################################################################
#
#       Get batch ends
#
##################################################################

def get_batch_ends(index_map, global_index_range_list, file_list, source_dict):
    """
    Generate the batch ends for each batch given all information.

    :param index_map: The map between global index and (file index, dataset index, local index)
    :param global_index_range_list: A numpy array containing the starting and ending global
                                    index of the corresponding batch
                [
       batch 0 -->  [starting global index, ending global index],
       batch 1 -->  [starting global index, ending global index],
       batch 2 -->  [starting global index, ending global index],
                        ...
                ]
    :param file_list: The list containing the file names.
    :param source_dict: The information of the source.
    :return: A list containing information for dask to retrieve the data in this batch.
             The structure of this variable is

        The first layer is a list ----->   [
                                        " This is for the first batch"
        The second layer is a dic ----->     {
                                              files :[ A list containing the addresses for files in this
                                                       folder. Notice that this list has the same order
                                                       as that listed in the input file list.]

                                              file name 1:
        The third layer is a dic  ----->                    {Dataset name:
        The forth layer is a list ----->                     [A list of the dataset names],

                                                             Ends:
                                                             [A list of the ends in the dataset. Each is a
                                                              small list: [start,end]]}
                                                             ,
                                              file name 2:
        The third layer is a dic  ----->                    {Dataset name:
        The forth layer is a list ----->                     [A list of the dataset names],

                                                             Ends:
                                                             [A list of the ends in the dataset. Each is a
                                                              small list: [start,end]]}
                                                             , ... }

                                         " This is for the second batch"
                                         ...
                                            ]
    """

    batch_number = global_index_range_list.shape[0]
    # Create a variable to hold batch ends.
    batch_ends_local = []

    for batch_idx in range(batch_number):

        global_idx_batch_start = global_index_range_list[batch_idx, 0]
        global_idx_batch_end = global_index_range_list[batch_idx, 1]

        # Create an element for this batch
        batch_ends_local.append({})
        # This entry contains the list of files contained in this batch
        batch_ends_local[-1].update({"files": []})

        # Find out how many h5 files are covered by this range
        """
        Because the way the map variable is created guarantees that the file index is 
        increasing, the returned result need not be sorted. Similar reason applies for 
        the other layers.
        """
        file_pos_holder = index_map[0, global_idx_batch_start: global_idx_batch_end]
        dataset_pos_holder = index_map[1, global_idx_batch_start: global_idx_batch_end]
        data_pos_holder = index_map[2, global_idx_batch_start: global_idx_batch_end]

        file_range = np.unique(file_pos_holder)

        # Create the entry for the batch
        for file_idx in file_range:

            # The file address of this file
            batch_ends_local[-1]["files"].append(file_list[file_idx])

            # Holder for dataset information for this file in this batch
            batch_ends_local[-1].update({file_list[file_idx]: {"Datasets": [],
                                                               "Ends": []}})
            # Find out which datasets are covered within this file for this batch
            dataset_range = np.unique(dataset_pos_holder[file_pos_holder == file_idx])
            for dataset_idx in dataset_range:
                # Attach this dataset name
                batch_ends_local[-1][file_list[file_idx]]["Datasets"].append(
                    source_dict[file_list[file_idx]]["Datasets"][dataset_idx])
                # Find out the ends for this dataset
                """
                Notice that, because later, I will use [start:end] to retrieve the data
                from the h5 file. Therefore, the end should be the true end of the python-style
                index plus 1.
                """
                tmp_start = np.min(
                    data_pos_holder[(file_pos_holder == file_idx) & (dataset_pos_holder == dataset_idx)])
                tmp_end = np.max(
                    data_pos_holder[(file_pos_holder == file_idx) & (dataset_pos_holder == dataset_idx)]) + 1
                # Attach this dataset range
                batch_ends_local[-1][file_list[file_idx]]["Ends"].append([tmp_start, tmp_end])

    return batch_ends_local


##################################################################
#
#       Provide batch index list to merge
#
##################################################################

@jit(int64[:, :](int64))
def get_batch_idx_per_list(batch_num):
    """
    The batch number is calculated in this way.

                --------------------------
                | 00 | 11 | 11 | 11 | 11 |
                --------------------------
                | 11 | 00 | 11 | 11 | 11 |
                --------------------------
                | 11 | 11 | 00 | 11 | 11 |
                --------------------------
                | 11 | 11 | 11 | 00 | 11 |
                --------------------------
                | 11 | 11 | 11 | 11 | 00 |
                --------------------------

    I want the index along each line for each 11 element.

    :param batch_num: The number of batches along each line.
    :return: A numpy array containing the dim1 idx of the 11 element in this matrix.
    """
    batch_num_per_line = batch_num - 1
    holder = np.zeros((batch_num, batch_num_per_line), dtype=np.int)

    # Deal with the first line and the last line
    holder[0, :] = np.arange(1, batch_num, dtype=np.int)
    holder[batch_num - 1, :] = np.arange(batch_num_per_line, dtype=np.int)
    for l in range(1, batch_num - 1):
        holder[l, :l] = np.arange(l, dtype=np.int)
        holder[l, l:] = np.arange(l, batch_num, dtype=np.int)

    return holder


##################################################################
#
#       IO functions
#
##################################################################


def save_distances(output_path, distance_patch, patch_position):
    """
    Save the distance patch to a numpy array.

    :param output_path: The folder to save the distance patch
    :param patch_position: the position of the patch in the large matrix. eg
                patch (0,0) | patch (0,1)
                --------------------------
                patch (1,0) | patch (1,1)

            The first number is the position along dimension zero. The second
            number is the position along dimension one.
    :param distance_patch: the distance patch to save
    """

    # load the data_source address
    address = output_path

    # check if the folder exist
    if not os.path.isdir(address + '/distances'):
        os.makedirs(address + '/distances')

    name = address + "/distances/patch_{}_{}.npy".format(patch_position[0], patch_position[1])
    np.save(name, distance_patch)


def assemble_mat(data_source, config):
    """
    Assemble different patches of distance matrices into a single distance matrix
    :param data_source: An instance of data_source class.
    :return: The 2D distance matrix. Notice that this matrix is up-triangular.
    """

    folder_address = data_source.output_path + '/distances'

    batch_num = data_source.batch_number
    total_num = data_source.pattern_number_total

    # First check if the address is a folder
    if not os.path.isdir(folder_address):
        raise Exception("The target specified by the folder_address is not a folder.\n" +
                        "Please make sure the folder_address is the folder where you have \n" +
                        "saved the distance patches.")

    # Second check whether all the patches are present in the folder
    flag = True  # True if all the patches exist.
    for l in range(batch_num):
        for m in range(l, batch_num):
            patch_file = folder_address + "/patch_{}_{}.npy".format(l, m)
            if not os.path.isfile(patch_file):
                flag *= False

    if not flag:
        raise Exception("The patches are not complete. \n" +
                        "Please check if you have obtained " +
                        "all {} patterns required to get a complete distance matrix.".format(
                            batch_num * (batch_num + 1) // 2))

    """
    If we have all the files, we can assemble the distance matrix.
    start_dim_0 record the starting point of the patch along axis 0.
    start_dim_1 record the starting point of the patch along axis 1.
    """
    holder = np.zeros((total_num, total_num))

    start_dim_0 = 0
    for l in range(batch_num):
        # Notice that the first dimension increases slower.
        end_dim_0 = start_dim_0 + data_source.batch_size_list[l]

        start_dim_1 = start_dim_0
        for m in range(l, batch_num):

            patch_file = folder_address + "/patch_{}_{}.npy".format(l, m)

            # load patch
            patch_holder = np.load(patch_file)
            # Check if the dimension is correct
            if patch_holder.shape[0] != data_source.batch_size_list[l] or patch_holder.shape[1] != \
                    data_source.batch_size_list[m]:

                print(patch_holder.shape, data_source.batch_size_list[l], data_source.batch_size_list[m])
                raise Exception("The size of the ({},{}) patch does not match that in the record.\n"
                                "Please check if the distance patch is correct.".format(l, m))
            else:

                end_dim_1 = start_dim_1 + data_source.batch_size_list[m]
                holder[start_dim_0:end_dim_0, start_dim_1:end_dim_1] = patch_holder
                start_dim_1 = end_dim_1

        # update the starting position of the outer loop.
        start_dim_0 = end_dim_0

    return holder

##################################################################
#
#       Assemble
#
##################################################################
