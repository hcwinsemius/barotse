#!/bin/bash -v
# this script warps the input layers of lisflood to a new (lower) resolution

export INPUT="/home/hcwinsemius/Barotse/Barotse_2019"
export OUTPUT="/home/hcwinsemius/Barotse/Barotse_500m"
gdalwarp -overwrite -tr 500 500 -r average -te 675000 8162500 848500 8454500 "$INPUT/bfplain.asc" "$OUTPUT/bfplain.tif"
gdal_translate -of AAIGRID "$OUTPUT/bfplain.tif" "$OUTPUT/bfplain.asc"

# make a PCRaster width map
gdal_translate -of PCRaster "$INPUT/width1.asc" "$OUTPUT/width.map"
gdal_translate -of PCRaster "$OUTPUT/bfplain.tif" "$OUTPUT/clone.map"
map2col "$OUTPUT/width.map" "$OUTPUT/width.col"

# make a new width file at lower resolution
col2map --clone "$OUTPUT/clone.map" -S "$OUTPUT/width.col" "$OUTPUT/width.map"

# translate PCRaster file to AAIGrid
gdal_translate -of AAIGRID "$OUTPUT/width.map" "$OUTPUT/width1.asc"

# copy all files needed
cp $INPUT/*.bdy $INPUT/*.bci $INPUT/*.par $INPUT/*.evap $OUTPUT
