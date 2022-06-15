#!/usr/bin/env python

import numpy as np
import rasterio
import sys, os
from datetime import datetime
import geopandas as gpd

# import Glofrim
from glofrim import Glofrim

# import barotse utils (first add path to be able to recognize it
sys.path.append('../utils')
import utils

# Setup the Glofrim object with the Glofrim .ini file
cbmi = Glofrim()
root_dir = os.path.abspath('.')
config_fn = os.path.join(root_dir, 'wflow_sfincs_1d2d_oneway.ini')
# define path name of sfincs boundary condition locations
fn_json = os.path.abspath("../sfincs/barotse/gis/src_update.geojson")

# read 1D boundary conditions source points explicitly
gdf_src = gpd.read_file(fn_json)

gdf_src_wfl = gdf_src.to_crs(4326)

# correcting mismatch in location to make sure runoff ends up in the model
x_off = np.zeros(len(gdf_src))
x_off[6] += -0.03333333
x_off[7] += 0.03333333


cbmi.logger.info('Reading config for cbmi model from {:s}'.format(config_fn))
cbmi.initialize_config(config_fn)
idxs_wfl = utils.get_indexes(cbmi, gdf_src_wfl, x_off=x_off)

# Set a start and end time interactively. Now just a couple of days for testing
t_start = datetime(2000, 1, 1)
t_end = datetime(2000, 12, 31)
cbmi.set_start_time(t_start)
cbmi.set_end_time(t_end)
try:
    t_start == cbmi.get_start_time()
    t_end == cbmi.get_end_time()
except:
    sys.exit('start or end time differ with set_var and get_var')
print('start time is: {:s}\nEnd time is {:s}'.format(t_start.strftime('%Y-%m-%d %H:%M:%S'), t_end.strftime('%Y-%m-%d %H:%M:%S')))

# Initialize the Glofrim coupled model instance
cbmi.logger.info('Initializing model')
cbmi.initialize_model()

# Run the model for a number of time steps and store results

# retrieve the subgrid channel elevation
#z = cbmi.bmimodels['LFP']._bmi.get_var('SGCz')
# retrieve the DEM
dem = cbmi.bmimodels['Sfincs'].get_value('zb')
H = []
f = []
c = []
Q = []
Qx = []
Qy = []
time = []
timesteps = 365
cbmi.logger.info('Running 1d2d experiment for {:d} timesteps'.format(timesteps))
# manually set exchange to additive
# cbmi.exchanges[1][1]['add'] = True

try:
    i = 0
    while i < timesteps:
        print(cbmi.get_current_time())
        cbmi.update()
        # utils.update_runoff_bounds(cbmi, idxs_wfl)
        flux_out = cbmi.bmimodels["WFL"].get_value_at_indices("RiverRunoff", idxs_wfl)
        flux_in = cbmi.bmimodels["Sfincs"]._bmi.get_var("qsrc")
        # overwrite discharges in all time steps
        flux_in[:] = flux_out
        cbmi.bmimodels["Sfincs"]._bmi.set_var("qsrc", flux_in)

        time.append(cbmi.get_current_time())
        h = cbmi.get_value('Sfincs.zs')
        # compute the flood_depth (above terrain)
        flood_depth = np.maximum(h-dem, 0)
        # compute channel depth (below terrain, only in channels)
        #channel_depth = np.minimum(dem-z, h)
        qx = cbmi.get_value('Sfincs.qx')
        qy = cbmi.get_value('Sfincs.qy')
        #qx_mod = 0.5*qx[:-1, :-1]+0.5*qx[:-1, 1:]
        #reverse flow so that positive is northward, and negative is southward
        #qy_mod = -0.5*qy[:-1, :-1]-0.5*qy[1:, :-1]
        # append all retrievals
        H.append(h)
        f.append(flood_depth)
        #c.append(channel_depth)
        #Q.append(cbmi.get_value('LFP.SGCQin'))
        Qx.append(qx)
        Qy.append(qy)
        i += 1
except Exception as e:
    print(e)
    sys.exit('something is going wrong in updating - please check!')

cbmi.logger.info('Setting up output structures')

# set up lists of names for all variables, lists of attributes dictionaries, and list of data
SFINCS_outputs = ['H', 'H_f', 'qx', 'qy']
SFINCS_attrs = [#{'units': 'm**3 s**-1',
             # 'short_name': 'river_flow',
             # 'long_name': 'River Flow'
             #},
             {'units': 'm',
              'short_name': 'water_level',
              'long_name': 'Water level +mean sea level'
             },
             {'units': 'm',
              'short_name': 'water_depth',
              'long_name': 'Water depth floodplain'
             },
             #{'units': 'm',
              #'short_name': 'water_depth',
              #'long_name': 'Water Depth channel'
             #},
             {'units': 'm**3 s**-1',
              'long_name': '10 metre U wind component'
             },
             {'units': 'm**3 s**-1',
              'long_name': '10 metre V wind component'
             }
            ]
datas = [#np.array(Q),
         np.array(H),
         np.array(f),
         #np.array(c),
         np.array(Qx),
         np.array(Qy),
        ]

# extract x and y axis from grid definition
xi, yi = np.meshgrid(np.arange(H[0].shape[1]), np.arange(H[0].shape[0]))
x = rasterio.transform.xy(cbmi.bmimodels['Sfincs'].grid.transform, yi[0,:].flatten(), xi[0,:].flatten())[0]
y = rasterio.transform.xy(cbmi.bmimodels['Sfincs'].grid.transform, yi[:,0].flatten(), xi[:,0].flatten())[1]

# put everything together in one ds, and store in file
cbmi.logger.info('Merging outputs to Dataset')
ds = utils.merge_outputs(datas, time, x, y, SFINCS_outputs, SFINCS_attrs)
# xr.merge([list_to_dataarray(data, t,xs, ys, name, attrs) for data, name, attrs in zip(datas, LFP_outputs, LFP_attrs)])
fn_out = os.path.abspath('test_oneyear_2D.nc')
cbmi.logger.info('Writing outputs to {:s}'.format(fn_out))
ds.to_netcdf(fn_out)

# close model
cbmi.logger.info('Closing model')
cbmi.finalize()


