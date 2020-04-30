# a number of utilities that can be used to store and analyze results of GLOFRIM
import fiona
import xarray as xr
import numpy as np
import rasterio
import rasterio.features
from scipy.signal import convolve2d

def perpendicular(line, reverse=False):
    """
    determines the direction of a perpendicular line
    input:
    :param line: - fiona LineString - line over which perpendicular direction needs to be determined
    :param reverse: boolean - default False (True), assuming that flow perpendicular direction is 90 degrees (counter)clockwise from the coordinate ordering of features.
    :return: (north, east) - tuple with signs of (north, east) directions, can be -1 (south, west), 1 (north, east) or 0 (no direction)
    """
    c1, c2 = line
    xdiff = c2[0] - c1[0]
    ydiff = c2[1] - c1[1]
    if reverse:
        north = np.sign(xdiff)
        east = -np.sign(ydiff)
    else:
        north = -np.sign(xdiff)
        east = np.sign(ydiff)
    return north, east

def discharge_f(da_x, da_y, feat, key='name', reverse=False):
    """
    Computes the flow over one single cross-section line (fiona feature) from two x-direction and y-direction flow fields
    :param da_x: DataArray - containing x-directional flow
    :param da_y: DataArray - containing x-directional flow
    :param feat: fiona single feature - (must be 2-coordinate LineString)
    :param key: string - name of fiona property (default: 'name') to use for naming of discharge cross section station
    :param reverse: boolean - default False (True), assuming that flow perpendicular direction is 90 degrees (counter)clockwise from the coordinate ordering of features.
    :return: flow: Dataset - containing all flow cross section time series
    """
    # determine affine
    x, y = da_x['x'].values, da_y['y'].values
    res_x, res_y = np.abs((x[-1] - x[0]) / (len(x) - 1)), np.abs((y[-1] - y[0]) / (len(y) - 1))
    xmin, xmax = x.min() - res_x * .5, x.max() + res_x * .5
    ymin, ymax = y.min() - res_y * .5, y.max() + res_y * .5
    height, width = da_x[0].shape
    transform = rasterio.transform.from_bounds(xmin, ymin, xmax, ymax, width, height)
    if feat is not None:
        if feat['geometry']['type'] != 'LineString':
            raise ValueError('Feature other than LineString found')
        if len(feat['geometry']['coordinates']) != 2:
            raise IndexError(
                'Non-straight lines found in cross-sections. Each cross-section line may only contain two coordinates')
        # determine the orientation of flow first, as perpendicular to the line direction
        north, east = perpendicular(feat['geometry']['coordinates'], reverse=reverse)
        if north == -1:
            north_south_conv = np.array([[0., -1., 0.], [0., 1, 0.], [0., 0., 0]])
        else:
            north_south_conv = np.array([[0., 0., 0.], [0., 1, 0.], [0., -1., 0]])
        if east == -1:
            west_east_conv = np.array([[0., 0., 0.], [0., 1, -1.], [0., 0., 0]])
        else:
            west_east_conv = np.array([[0., 0., 0.], [-1., 1, 0.], [0., 0., 0]])
        # rasterize the line
        image = rasterio.features.rasterize([(feat['geometry'], 1)],
                                            out_shape=da_y[0].shape,
                                            transform=transform,
                                            all_touched=True
                                            )
        # find cells that should be considered when determining flow in south-north and west-east direction
        # give these cells a number to determine if flow is negative or positive
        north_south_cells = np.maximum(convolve2d(image, north_south_conv, mode='same'), 0) * north
        west_east_cells = np.maximum(convolve2d(image, west_east_conv, mode='same'), 0) * east
        cs = xr.DataArray(image, name='cross_section',
                          dims=('y', 'x'),
                          coords={'y': da_y['y'],
                                  'x': da_y['x'],
                                  },
                          )
        ns = xr.DataArray(north_south_cells, name='north_south',
                          dims=('y', 'x'),
                          coords={'y': da_y['y'],
                                  'x': da_x['x'],
                                  },
                          )
        we = xr.DataArray(west_east_cells, name='west_east',
                          dims=('y', 'x'),
                          coords={'y': da_y['y'],
                                  'x': da_x['x'],
                                  },
                          )
        flow_directions = xr.merge([cs, ns, we])
        flow_y = (da_y * flow_directions['north_south']).sum(dim=('x', 'y'))

        flow_x = (da_x * flow_directions['west_east']).sum(dim=('x', 'y'))
        flow = flow_x + flow_y
        flow.name = feat['properties']['name']
        flow.attrs['units'] = da_x.units
        flow.attrs['short_name'] = 'river_discharge'

        return flow
    else:
        return None

def discharge(da_x, da_y, feats, key='name', reverse=False):
    """
    Wrapper function to compute discharge over line segments in a geopackage (opened with fiona)

    :param da_x: DataArray - containing x-directional flow
    :param da_y: DataArray - containing x-directional flow
    :param feats: fiona features - (must be 2-coordinate LineStrings only!)
    :param key: string - name of fiona property (default: 'name') to use for naming of discharge cross section stations
    :param reverse: boolean - default False (True), assuming that flow perpendicular direction is 90 degrees (counter)clockwise from the coordinate ordering of features.
    :return: flow: Dataset - containing all flow cross section time series
    """
    qs = [discharge_f(da_x, da_y, feat, key, reverse=reverse) for feat in feats]
    qs = [i for i in qs if i is not None]
    return xr.merge(qs)
