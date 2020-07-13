#!/usr/bin/env python

import numpy as np
import rasterio
import sys, os
from datetime import datetime

# import Glofrim
from glofrim import Glofrim

# import barotse utils (first add path to be able to recognize it
sys.path.append('../utils')
import utils
# from utils import update_funcs
Glofrim.update = utils.update_funcs.update_glofrim
Glofrim._models['LFP'].update = utils.update_funcs.update_lfp
# Setup the Glofrim object with the Glofrim .ini file
cbmi = Glofrim()
root_dir = os.path.abspath('.')
config_fn = os.path.join(root_dir, 'glofrim_barotse_2way1D2D.ini')
cbmi.logger.info('Reading config for cbmi model from {:s}'.format(config_fn))
cbmi.initialize_config(config_fn)

# Set a start and end time interactively. Now just a couple of days for testing
t_start = datetime(2000,10,1)
t_end = datetime(2001,10,1)
# t_end = datetime(2000,1,6)
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
z = cbmi.bmimodels['LFP']._bmi.get_var('SGCz')
# retrieve the DEM
dem = cbmi.bmimodels['LFP']._bmi.get_var('DEM')
H = []
f = []
c = []
Q = []
Qx = []
Qy = []
time = []
timesteps = 365
cbmi.logger.info('Running 2-way 1d2d experiment for {:d} timesteps'.format(timesteps))
# manually set exchange to additive
cbmi.exchanges[2][1]['add'] = True

# make a projection function from LFP to WFL
wfl_grid = cbmi.bmimodels['WFL'].grid
lfp_grid = cbmi.bmimodels['LFP'].grid
reproject_lfp_wflow = lambda data, nodata: rasterio.warp.reproject(
    data,
    destination=np.zeros((wfl_grid.height, wfl_grid.width)),
    src_transform=lfp_grid.transform,
    src_crs=lfp_grid.crs,
    src_nodata=nodata,
    dst_transform=wfl_grid.transform,
    dst_crs=wfl_grid.crs,
    dst_nodata=nodata,
    resampling=rasterio.enums.Resampling.average
    )[0]


try:
    i = 0
    while i < timesteps:
        print(cbmi.get_current_time())
        # cbmi.update()

        # run wflow and lfp (inc. reinfiltration) for one step (assuming infiltration rate of 30./86400 mm per second)
        cbmi.update(infiltcap=30. / 86400, storagecap=1e6)

        # retrieve and reproject infiltration to wflow grid
        infilt_wfl = reproject_lfp_wflow(cbmi.bmimodels['LFP'].infilt, np.nan)

        # remove any missing values to prevent model crash
        infilt_wfl[np.isnan(infilt_wfl)] = 0.

        # add infiltration to snow water store so that it will infiltrate into wflow in the next step
        snow = cbmi.bmimodels['WFL']._bmi.get_value('Snow')
        snow += np.flipud(infilt_wfl)
        cbmi.bmimodels['WFL']._bmi.set_value('Snow', snow)

        # administer the current time step outputs
        time.append(cbmi.get_current_time())
        h = cbmi.get_value('LFP.H')

        # compute the flood_depth (above terrain)
        flood_depth = np.maximum(h+z-dem, 0)
        # compute channel depth (below terrain, only in channels)
        channel_depth = np.minimum(dem-z, h)
        qx = cbmi.get_value('LFP.Qx')
        qy = cbmi.get_value('LFP.Qy')
        qx_mod = 0.5*qx[:-1, :-1]+0.5*qx[:-1, 1:]
        # reverse flow so that positive is northward, and negative is southward
        qy_mod = -0.5*qy[:-1, :-1]-0.5*qy[1:, :-1]
        # reverse flow so that positive is northward, and negative is southward
        # append all retrievals
        H.append(h)
        f.append(flood_depth)
        c.append(channel_depth)
        Q.append(cbmi.get_value('LFP.SGCQin'))
        Qx.append(qx_mod)
        Qy.append(qy_mod)
        i += 1
except Exception as e:
    print(e)
    sys.exit('something is going wrong in updating - please check!')

cbmi.logger.info('Setting up output structures')

# set up lists of names for all variables, lists of attributes dictionaries, and list of data
LFP_outputs = ['SGCQin', 'H', 'H_f', 'H_c', 'Qx', 'Qy']
LFP_attrs = [{'units': 'm**3 s**-1',
              'short_name': 'river_flow',
              'long_name': 'River Flow'
             },
             {'units': 'm',
              'short_name': 'water_depth',
              'long_name': 'Water Depth'
             },
             {'units': 'm',
              'short_name': 'water_depth',
              'long_name': 'Water Depth floodplain'
             },
             {'units': 'm',
              'short_name': 'water_depth',
              'long_name': 'Water Depth channel'
             },
             {'units': 'm**3 s**-1',
              'long_name': '10 metre U wind component'
             },
             {'units': 'm**3 s**-1',
              'long_name': '10 metre V wind component'
             }
            ]
datas = [np.array(Q),
         np.array(H),
         np.array(f),
         np.array(c),
         np.array(Qx),
         np.array(Qy),
        ]

# extract x and y axis from grid definition
xi, yi = np.meshgrid(np.arange(Q[0].shape[1]), np.arange(Q[0].shape[0]))
x = rasterio.transform.xy(cbmi.bmimodels['LFP'].grid.transform, yi[0,:].flatten(), xi[0,:].flatten())[0]
y = rasterio.transform.xy(cbmi.bmimodels['LFP'].grid.transform, yi[:,0].flatten(), xi[:,0].flatten())[1]

# put everything together in one ds, and store in file
cbmi.logger.info('Merging outputs to Dataset')
ds = utils.merge_outputs(datas, time, x, y, LFP_outputs, LFP_attrs)
# xr.merge([list_to_dataarray(data, t,xs, ys, name, attrs) for data, name, attrs in zip(datas, LFP_outputs, LFP_attrs)])
fn_out = os.path.abspath('test2_oneyear_2way_1D2D.nc')
cbmi.logger.info('Writing outputs to {:s}'.format(fn_out))
encoding = {name: {'zlib': True} for name in LFP_outputs}
ds.to_netcdf(fn_out, encoding=encoding)

# close model
cbmi.logger.info('Closing model')
cbmi.finalize()


