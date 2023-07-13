#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
-----------------------------------------------------------------------------
  Copyright (C) 2023 University of Basel. All rights reserved.

  This program is free software; you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation; either version 2 of the License, or
  (at your option) any later version.
  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License along
  with this program; if not, write to the Free Software Foundation, Inc.,
  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

------------------------------------------------------------------------------

Description:
This script converts a Dataset of ND2 images to a Plate.
Important the ND2 images need to have file names starting like e.g.:
"WellB3_ ....nd2"
Which is the default if JOB acquisitions when choosing
"Split Storage per Well".
The script will take care of placing the FOVs into the correct well.

@author Loïc Sauteur (based on Will Moor's "Dataset_To_Plate.py" v4.3(.2)
<a href="mailto:loic.sauteur@unibas.ch">loic.sauteur@unibas.ch</a>

"""

__version__ = "0.0.1"
__author__ = "Loïc Sauteur"
__mail__ = "loic.sauteur@unibas.ch"
__institution__ = "University of Basel"


from omero.gateway import BlitzGateway
import omero
import omero.scripts as scripts

from omero.rtypes import rint, rlong, rstring, robject, unwrap


def add_images_to_plate(conn,
                        images,
                        plate_id,
                        column, row,
                        remove_from=None):
    """
    Creates wells and adds images to wells of a plate
    :param conn: BlitzGateway
    :param images: List of image objects
    :param plate_id: integer plate ID
    :param column: Integer
    :param row: Integer
    :param remove_from: Bool (if to remove the images form the dataset)
    :return: boolean,
        in case Exception was raised when images are added to wells,
        it will be False. Otherwise, True (upon function end)
    """

    update_service = conn.getUpdateService()

    well = omero.model.WellI()
    well.plate = omero.model.PlateI(plate_id, False)
    well.column = rint(column)
    well.row = rint(row)

    try:
        for image in images:
            ws = omero.model.WellSampleI()
            ws.image = omero.model.ImageI(image.id, False)
            ws.well = well
            well.addWellSample(ws)
        update_service.saveObject(well)
    except Exception:
        return False

    # remove from Dataset
    for image in images:
        if remove_from is not None:
            links = list(image.getParentLinks(remove_from.id))
            link_ids = [l.id for l in links]
            conn.deleteObjects('DatasetImageLink', link_ids)
    return True


def dataset_to_plate(conn, script_params, dataset_id, screen):
    """
    This function will put a single dataset into the specified screen.
    It is a modified version of the original script "Dataset_To_Plate.py".
    Main modification are about the sorting of images, and checking for erros.
    :param conn: BlitzGateway
    :param script_params: dict of script parameters
    :param dataset_id: integer for dataset
    :param screen: ScreenI object
    :return:
        plate: PlateI object
        link: ScreenPlateLinkI object
        delete_handle: List, for deleting the dataset
        message: String, describing an error, or None if no error
    """

    message = ""  # variable to return errors

    dataset = conn.getObject("Dataset", dataset_id)
    if dataset is None:
        return

    update_service = conn.getUpdateService()
    # create Plate
    plate = omero.model.PlateI()
    plate.name = omero.rtypes.RStringI(dataset.name)
    plate.columnNamingConvention = rstring("number")  # always for nd2
    plate.rowNamingConvention = rstring("letter")  # always for nd2
    plate = update_service.saveAndReturnObject(plate)

    if screen is not None and screen.canLink():
        link = omero.model.ScreenPlateLinkI()
        link.parent = omero.model.ScreenI(screen.id, False)
        link.child = omero.model.PlateI(plate.id.val, False)
        update_service.saveObject(link)
    else:
        link = None

    # sort images by name
    images = list(dataset.listChildren())
    dataset_img_count = len(images)
    if "Filter_Names" in script_params:
        filter_by = script_params["Filter_Names"]
        images = [i for i in images if i.getName().find(filter_by) >= 0]
    images.sort(key=lambda x: x.name.lower())

    # Do we try to remove images from Dataset & Delete Dataset when/if empty?
    remove_from = None
    remove_dataset = "Remove_From_Dataset" in script_params and \
                     script_params["Remove_From_Dataset"]
    if remove_dataset:
        remove_from = dataset

    # @modification: instead of putting the sorted images to wells,
    #  the images are sorted into wells according to their name
    # Dictionary with image list per well-identifier (String)
    well_fovs = {}  # will be e.g. "A1": [imageX, imageY]
    for image in images:
        # abort if imageName does not contain "Well"
        if not image.getName().startswith('Well'):
            message += "Error: could not find 'Well' in image: "
            message += image.getName()
            return None, None, None, message

        # images are called something like: "WellB2_...."
        wellName = image.getName().split("_")[0].replace("Well", "")

        wellName = wellName.replace("Well", "")
        if wellName not in well_fovs:
            well_fovs[wellName] = [image]
        else:
            well_fovs[wellName].append(image)

    images_per_well = None
    for wellName in well_fovs.keys():
        if images_per_well is None:
            images_per_well = len(well_fovs[wellName])
        else:
            # Return message if FOVs per well does not match for all images
            if images_per_well != len(well_fovs[wellName]):
                message += "Error: not all wells seem to " \
                           "have the same number of FOV"
                return None, None, None, message

    # create a dictionary to match row letters with corresponding numbers
    row_numbers = {}
    for i in range(1, 25):
        row_numbers[chr(64 + i)] = i

    # eventually, add images to plate
    for wellName, images in well_fovs.items():
        # mind the 0-based index
        row_letter = str(wellName[0])
        col_number = int(wellName[1:]) - 1
        row_number = row_numbers[row_letter] - 1

        added_count = add_images_to_plate(conn, images,
                                          plate.getId().getValue(),
                                          col_number, row_number,
                                          remove_from)
        # Info: added_count is from the original dataset_to_plate.py
        # it makes not much sense here since it gets a boolean value

    # if user wanted to delete dataset, AND it's empty we can delete dataset
    delete_dataset = False  # Turning this functionality off for now.
    delete_handle = None
    if delete_dataset:
        if dataset_img_count == added_count:
            dcs = list()
            options = None  # {'/Image': 'KEEP'}    # don't delete the images!
            dcs.append(omero.api.delete.DeleteCommand(
                "/Dataset", dataset.id, options))
            delete_handle = conn.getDeleteService().queueDelete(dcs)
    return plate, link, delete_handle, None


def datasets_to_plates(conn: BlitzGateway, script_params):
    """
    This function will handle multiple datasets.
    It is heavily based on the original script Dataset_To_Plate.py,
    with small modifications (mostly concerning the script_params)

    :param conn:  BlitzGateway
    :param script_params: probably a dictionary of the script_parameters
    :return:
        robj = the screen object
        message = String
    """
    update_service = conn.getUpdateService()  # from original dataset_to_plate
    message = ""  # from original dataset_to_plate

    # get the script parameters     -------------------------------------------
    dtype = script_params['Data_Type']
    ids = script_params['IDs']

    # Get the datasets ID
    datasets = list(conn.getObjects(dtype, ids))

    # Exclude datasets containing images already linked to a well
    n_datasets = len(datasets)
    datasets = [x for x in datasets if not has_images_linked_to_well(conn, x)]
    if len(datasets) < n_datasets:
        message += "Excluded %s out of %s dataset(s). " \
                   % (n_datasets - len(datasets), n_datasets)

    # Return if all input dataset are not found or excluded
    if not datasets:
        return None, message

    # Filter dataset IDs by permissions
    ids = [ds.getId() for ds in datasets if ds.canLink()]
    if len(ids) != len(datasets):
        perm_ids = [str(ds.getId()) for ds in datasets if not ds.canLink()]
        message += "You do not have the permissions to add the images from" \
                   " the dataset(s): %s." % ",".join(perm_ids)
    if not ids:
        return None, message

    # find or create Screen if specified
    screen = None
    newscreen = None
    if "Screen" in script_params and len(script_params["Screen"]) > 0:
        s = script_params["Screen"]
        # see if this is ID of existing screen
        try:
            screen_id = int(s)
            screen = conn.getObject("Screen", screen_id)
        except ValueError:
            pass
        # if not, create one
        if screen is None:
            newscreen = omero.model.ScreenI()
            newscreen.name = rstring(s)
            newscreen = update_service.saveAndReturnObject(newscreen)
            screen = conn.getObject("Screen", newscreen.getId().getValue())

    plates = []
    links = []
    deletes = []
    for dataset_id in ids:
        # This is where individual datasets are put into a plate
        plate, link, delete_handle, message1 = dataset_to_plate(conn,
                                                                script_params,
                                                                dataset_id,
                                                                screen)
        if message1 is not None:
            # @modification: addition compared to the original version
            # return/abort. Causes: different number of FOVs per well, or
            #   image names do not start with 'Well'
            return None, message1

        if plate is not None:
            plates.append(plate)
        if link is not None:
            links.append(link)
        if delete_handle is not None:
            deletes.append(delete_handle)

    # wait for any deletes to finish
    for handle in deletes:
        cb = omero.callbacks.DeleteCallbackI(conn.c, handle)
        while True:  # ms
            if cb.block(100) is not None:
                break

    if newscreen:
        message += "New screen created: %s." % newscreen.getName().getValue()
        robj = newscreen
    elif plates:
        robj = plates[0]
    else:
        robj = None

    if plates:
        if len(plates) == 1:
            plate = plates[0]
            message += " New plate created: %s" % plate.getName().getValue()
        else:
            message += " %s plates created" % len(plates)
        if len(plates) == len(links):
            message += "."
        else:
            message += " but could not be attached."
    else:
        message += "No plate created."
    return robj, message


def has_images_linked_to_well(conn, dataset):
    """
    Helper method from original dataset_to_plate.
    Used to be located within the
    datasets_to_plates(conn, script_params) function.
    :param conn: BlitzGateway
    :param dataset: DatasetI, I think
    :return: Bool
    """
    params = omero.sys.ParametersI()
    query = "select count(well) from Well as well "\
            "left outer join well.wellSamples as ws " \
            "left outer join ws.image as img "\
            "where img.id in (:ids)"
    params.addIds([i.getId() for i in dataset.listChildren()])
    n_wells = unwrap(conn.getQueryService().projection(
        query, params, conn.SERVICE_OPTS)[0])[0]
    if n_wells > 0:
        return True
    else:
        return False


def run_script():
    """
    The main entry point of the script...
    """
    print('started: run_script')
    data_types = [rstring('Dataset')]
    # n_wells = [rstring('24'), rstring('48'), rstring('96'), rstring('384')]

    client = scripts.client(
        'ND2_Dataset_to_Plate.py',
        """ Take a Dataset of ND2 images and put them into a new Plate, \
        arranging them into row and columns according to the file name.
        Important, image names must follow this naming pattern: 'WellD11_....'
        """,

        scripts.String(
            "Data_Type", optional=False, grouping="1",
            description="Choose source of images (only Dataset supported)",
            values=data_types, default="Dataset"),

        scripts.List(
            "IDs", optional=False, grouping="2",
            description="List of Dataset IDs to convert to new"
                        " Plates.").ofType(rlong(0)),

        scripts.String(
            "Filter_Names", grouping="2.1",
            description="Filter the images by names that contain this value"),

        # did not use following script parameter
        #scripts.String(
        #    "Well_plate_format", grouping="3", optional=False, default='96',
        #    values=n_wells,
        #    description="""Number of wells that the plate could contain."""),

        scripts.String(
            "Screen", grouping="4",
            description="Option: put Plate(s) in a Screen. Enter Name of new"
                        " screen or ID of existing screen"),

        scripts.Bool(
            "Remove_From_Dataset", grouping="5", default=True,
            description="Remove Images from Dataset as they are added to"
                        " Plate"),

        version=__version__,
        authors=[__author__, "DBM"],
        institutions=[__institution__],
        contact=__mail__,
    )
    try:
        script_params = client.getInputs(unwrap=True)

        # wrap client to use the Blitz Gateway
        conn = BlitzGateway(client_obj=client)

        # convert Dataset(s) to Plate(s). Returns new plates or screen
        new_obj, message = datasets_to_plates(conn, script_params)

        client.setOutput("Message", rstring(message))
        if new_obj:
            client.setOutput("New_Object", robject(new_obj))

    finally:
        client.closeSession()


if __name__ == "__main__":
    print('started')
    run_script()
