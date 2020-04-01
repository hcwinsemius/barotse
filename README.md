# barotse
Simulation framework for interactions in Barotse floodplain

# LISFLOOD
To get variables from lisflood models, use the get_var property in the bmi instance. The following variables are available (copy-pasted from the bmi c++ code of lisflood)
H: water depth [m]
DEM: terrain level [m]
Qx: x-directional flow over 2D-grid
Qy: y-directional flow over 2D-grid
rain: rain-on-grid (not tested, unit not known)
dx: x-coordinate step size (constant) [m]
dy: y-coordinate step size (constant) [m]
dx_sqrt: sqrt of dx
dA: cell surface [m2]
SGCwidth: sub-grid channel width [m]
SGCQin: sub-grid channel inflow [m3/s]
SGCz: sub-grid channel depth [m]


blx: unknown TODO
bly: unknown TODO
BC.numPS: unknown (boundary conditions?)
BC.xpi: unknown
BC.ypi: unknown
QxSGold: unknown
QySGold: unknown
