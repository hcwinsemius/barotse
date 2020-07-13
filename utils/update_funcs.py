# these functions are monkey patches to the standard glofrim update functions.
# They ensure that you introduce a infiltration with certain conditions on lisflood-FP and that infiltration
# is returned from the model after each day running so that it can be introduced to WFLOW again

import numpy as np

def update_glofrim(self, dt=None, **kwargs):
    """Updating model for a certain time step interval (default: None).
    checks whether model end time is already reached;
    requires that model-specific time step is a whole number of update time step.

    Keyword Arguments:
        dt {int} -- update time step interval [sec] at which information is exchanged between models (default: {None})

    Raises:
        Warning -- Raised in models are not initialized before updating
        Exception -- Raised if model end time is already reached; no further updating possible
    """
    from datetime import timedelta

    if not self.initialized:
        msg = "models should be initialized first"
        self.logger.warn(msg)
        raise Warning(msg)
    if self._t >= self.get_end_time():
        msg = "endTime already reached, model not updated"
        self.logger.warn(msg)
        raise Exception(msg)
    # update all models with combined model dt
    wb_dict = {'time': str(self._t)}
    dt = self._dt.total_seconds() if dt is None else dt
    t_next = self._t + timedelta(seconds=dt)
    for item in self.exchanges:
        if item[0] == 'update':
            # LFP deviates from the set timestep using an adaptive timestep if dt is set to large
            # calculate the dt to get to the next timestep
            # NOTE we use "update" instead of "update_until" to getter better logging.
            imod = item[1]
            dt_mod = (t_next - self.bmimodels[imod]._t).total_seconds()
            # adapted for infiltration H.C. Winsemius
            if imod == 'LFP':
                self.bmimodels[imod].update(dt=dt_mod, **kwargs)
            else:
                self.bmimodels[imod].update(dt=dt_mod)

            # get volume totals in and out if the bmi object has this funtion, ortherwise return -9999
            tot_volume_in = getattr(self.bmimodels[imod], '_get_tot_volume_in', lambda: -9999.)()
            wb_dict.update({'{}_tot_in'.format(imod): '{:.2f}'.format(tot_volume_in)})
            tot_volume_out = getattr(self.bmimodels[imod], '_get_tot_volume_out', lambda: -9999.)()
            wb_dict.update({'{}_tot_out'.format(imod): '{:.2f}'.format(tot_volume_out)})
        elif item[0] == 'exchange':
            tot_volume = self.exchange(**item[1])
            wb_dict.update({item[1]['name']: '{:.2f}'.format(tot_volume)})
    # write water balance volumes to file according to header
    self.wb_logger.info(', '.join([wb_dict[c] for c in self._wb_header]))
    self._t = self.get_current_time()


def update_lfp(self, dt=None, infiltcap=None, storagecap=None, infiltdt=3600):
    """
    refactoring (monkey patch) of lisflood GLOFRIM update function to be able to account for infiltration
    inputs:
        dt: time step in secs. (if not specified, taken from model instance)
        infiltcap: infiltration capacity in mm s-1
        storagecap: available storage capacity left over in the soil in mm
        infiltdt: frequency by which to update the infiltration

    """

    def infilt():
        """
        Determine infiltration over time step
        """
        # get water level above channel depth
        h = self._bmi.get_var('H')
        flood_depth = np.maximum(h + z - dem, 0)
        current_infilt_cap = infiltcap * ((
                                                      self._t - t_current_infilt).total_seconds()) / 1000  # infiltration capacity within sub-time step (in m total)
        potential_infilt = np.minimum(storagecap / 1000 - total_infiltration,
                                      current_infilt_cap)  # infiltration maximized to capacity currently available in soil
        return np.minimum(flood_depth, potential_infilt)

    from datetime import datetime, timedelta

    # make a zero infiltration map [mm accumulated over time step]
    total_infiltration = np.zeros(self.grid.mask.shape)
    if infiltcap is None:
        infiltcap = np.ones(self.grid.mask.shape) * 1e6  # super large infiltration capacity
    if storagecap is None:
        storagecap = np.zeros(self.grid.mask.shape)

    # dt in seconds. if not given model timestep is used
    if self._t >= self._endTime:
        raise Exception("endTime already reached, model not updated")
    if (dt is not None) and (dt != self._dt.total_seconds()):
        dt = timedelta(seconds=dt)
        # because of the adaptive timestep scheme do not check the dt value
        # if not glib.check_dts_divmod(dt, self._dt):
        #     msg = "Invalid value for dt in comparison to model dt. Make sure a whole number of model timesteps ({}) fit in the given dt ({})"
        #     raise ValueError(msg.format(self._dt, dt))
    else:
        dt = self._dt
    t_next = self.get_current_time() + dt
    t_current_infilt = self.get_current_time()
    t_next_infilt = t_current_infilt + timedelta(seconds=infiltdt)
    i = 0
    t_current = self.get_current_time()
    z = self._bmi.get_var('SGCz')
    # retrieve the DEM
    dem = self._bmi.get_var('DEM')

    while self._t < t_next:
        self._bmi.update()
        self._t = self.get_current_time()
        if self._t > t_next_infilt:
            #             print('Seconds past: {:d}'.format(int((self._t - t_current_infilt).total_seconds())))
            actual_infilt = infilt()
            total_infiltration += actual_infilt  # add current infiltration to total over entire GLOFRIM timestep
            h = self._bmi.get_var('H')
            h -= actual_infilt  # reduce water depth by infiltration amount, this should automatically also update h in lisflood itself
            # update the next time step to store infilt
            t_current_infilt = self._t
            t_next_infilt = self._t + timedelta(seconds=infiltdt)
        i += 1
    if self._t > t_current_infilt:
        # do one final infiltration update
        #         print('Seconds past: {:d}'.format(int((self._t - t_current_infilt).total_seconds())))
        actual_infilt = infilt()
        total_infiltration += actual_infilt  # add current infiltration to total over entire GLOFRIM timestep
        h = self._bmi.get_var('H')
        h -= actual_infilt

    self.logger.info('updated model to datetime {} in {:d} iterations'.format(self._t.strftime("%Y-%m-%d %H:%M:%S"), i))
    self.infilt = total_infiltration * 1000
#     return total_infiltration * 1000 # return this in mm over time step