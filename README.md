# omero-scripts
----------

### ND2_Dataset_To_Plate.py:
Nikon ND2 well plate images uploaded to OMERO land in datasets, rahter than screens.

This script will move these dataset images to an OMERO screen plate.

It will associate the images to OMERO wells, according to the image name,
based on their name with follwoing pattern:

`"WellC11_*.nd2"`

If the image names do not start with 'Well', the script will not move the images.

Multiple fields per well are supported.

#### Script parameters:
`Dataset ID`: of the images to be moved.

`Filter Name`: String to filter for subsets of images.

`Screen`: (optional) ID of existing screen, to add the images as plate. If not supplied, a new one is generated.

`Remove from Dataset`: Boolean, if to remove the images from the source dataset.


**This script is based on Will Moore's `Dataset_To_Plate.py` [OMERO script](https://github.com/ome/omero-scripts/blob/develop/omero/util_scripts/Dataset_To_Plate.py).**

----------
