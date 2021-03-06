# pylint: disable=C0103
'''
Contains the Pendulum envionment, along with default parameters and
a rendering class
'''
import numpy as np

from gym import spaces
from matplotlib import pyplot as plt

from kusanagi.shell import plant
from kusanagi.shell import cost
from kusanagi import utils


def default_params():
    # setup learner parameters
    angi = [0]
    x0 = np.array([0, 0])
    S0 = np.eye(len(x0))*(0.2**2)
    p0 = utils.distributions.Gaussian(x0, S0)
    x0a, S0a = utils.gTrig2_np(x0[None, :], np.array(S0)[None, :, :],
                               angi, len(x0))

    # plant parameters
    plant_params = {}
    #plant_params['dt'] = 0.1
    plant_params['dt'] = 0.05
    plant_params['pole_length'] = 1.0
    plant_params['pole_mass'] = 1.0
    #plant_params['friction'] = 0.01
    plant_params['friction'] = 0.
    #plant_params['gravity'] = 9.82
    plant_params['gravity'] = 10.
    plant_params['state0_dist'] = p0
    plant_params['noise_dist'] = utils.distributions.Gaussian(
        np.zeros((p0.dim,)),
        np.diag([0.01,0.1])**2)

    # policy parameters
    policy_params = {}
    policy_params['state0_dist'] = p0
    policy_params['angle_dims'] = angi
    policy_params['n_inducing'] = 20
    #policy_params['maxU'] = [2.5]
    policy_params['maxU'] = [2.]

    # dynamics model parameters
    dynmodel_params = {}
    dynmodel_params['idims'] = x0a.size + len(policy_params['maxU'])
    dynmodel_params['odims'] = x0.size
    dynmodel_params['n_inducing'] = 100

    # cost function parameters
    cost_params = {}
    cost_params['angle_dims'] = angi
    cost_params['target'] = [np.pi, 0]
    #cost_params['target'] = [1., 0., 0.]
    cost_params['cw'] = 0.5
    cost_params['expl'] = 0.0
    cost_params['pole_length'] = plant_params['pole_length']
    cost_params['loss_func'] = cost.quadratic_saturating_loss

    # optimizer params
    opt_params = {}
    opt_params['max_evals'] = 100
    opt_params['conv_thr'] = 1e-16
    opt_params['min_method'] = 'L-BFGS-B'

    # general parameters
    params = {}
    params['state0_dist'] = p0
    params['angle_dims'] = angi
    #params['min_steps'] = int(4.0/plant_params['dt'])  # control horizon
    #params['max_steps'] = int(4.0/plant_params['dt'])  # control horizon
    params['min_steps'] = 35
    params['max_steps'] = 35
    params['discount'] = .995                           # discount factor

    params['plant'] = plant_params
    params['policy'] = policy_params
    params['dynamics_model'] = dynmodel_params
    params['cost'] = cost_params
    params['optimizer'] = opt_params

    return params


def pendulum_loss(mx, Sx,
                  target=np.array([np.pi, 0]),
                  angle_dims=[0],
                  pole_length=0.5,
                  cw=[0.25],
                  *args, **kwargs):
    # size of target vector (and mx) after replacing angles with their
    # (sin, cos) representation:
    # [x1,x2,..., angle,...,xn] -> [x1,x2,...,xn, sin(angle), cos(angle)]
    Da = np.array(target).size + len(angle_dims)

    #target = np.array([1., 0., 0.])
    #angle_dims = None
    #Q = np.eye(len(target))

    # build cost scaling function
    Q = np.zeros((Da, Da))
    Q[0, 0] = 1
    Q[0, -2] = pole_length
    Q[-2, 0] = pole_length
    Q[-2, -2] = pole_length**2
    Q[-1, -1] = pole_length**2

    return cost.distance_based_cost(
        mx, Sx, target, Q, cw, angle_dims=angle_dims, *args, **kwargs)


class Pendulum(plant.ODEPlant):

    metadata = {
        'render.modes': ['human']
    }

    def __init__(self, pole_length=1.0, pole_mass=1.0,
                 friction=0.01, gravity=9.82,
                 state0_dist=None,
                 loss_func=None,
                 name='Pendulum',
                 *args, **kwargs):
        super(Pendulum, self).__init__(name=name, loss_func=loss_func, *args, **kwargs)
        # pendulum system parameters
        self.l = pole_length
        self.m = pole_mass
        self.b = friction
        self.g = gravity

        '''
        # initial state
        if state0_dist is None:
            self.state0_dist = utils.distributions.Gaussian(
                [0, 0, 0, 0], (0.1**2)*np.eye(4))
        else:
            self.state0_dist = state0_dist
        '''

        # pointer to the class that will draw the state of the carpotle system
        #self.renderer = None

        self.max_speed = 8.
        self.max_torque = 2.
        self.dt = .05
        #self.viewer = None

        high = np.array([1., 1., self.max_speed])
        self.action_space = spaces.Box(low=-self.max_torque, high=self.max_torque, shape=(1,))
        self.observation_space = spaces.Box(low=-high, high=high)

        '''
        o_lims = np.array([np.inf for i in range(2)])
        self.observation_space = spaces.Box(-o_lims, o_lims)
        # 1 action dim (x_force)
        a_lims = np.array([np.finfo(np.float).max for i in range(1)])
        self.action_space = spaces.Box(-a_lims, a_lims)
        '''

    def dynamics(self, t, z):
        l, m, b, g = self.l, self.m, self.b, self.g
        f = self.u if self.u is not None else np.array([0])

        a1 = m*l
        dz = np.zeros((2, 1))
        dz[0] = z[1]                                           # theta
        dz[1] = 3*(f - b*z[1] - 0.5*a1*g*np.sin(z[0]))/(a1*l)  # dtheta/dt

        return dz

    def step(self,u):
        th, thdot = self.state # th := theta

        g = 10.
        m = 1.
        l = 1.
        dt = self.dt

        u = np.clip(u, -self.max_torque, self.max_torque)[0]
        self.last_u = u # for rendering
        costs = angle_normalize(th)**2 + .1*thdot**2 + .001*(u**2)

        newthdot = thdot + (-3*g/(2*l) * np.sin(th + np.pi) + 3./(m*l**2)*u) * dt
        newth = th + newthdot*dt
        newthdot = np.clip(newthdot, -self.max_speed, self.max_speed) #pylint: disable=E1111

        self.state = np.array([newth, newthdot])
        return self._get_obs(), costs, False, {}

    def reset(self):
        #state0 = self.state0_dist()
        high = np.array([np.pi, 1.])
        #self.state = self.np_random.uniform(low=-high, high=high)
        #self.state = state0.copy()
        self.state = np.random.uniform(low=-high, high=high)
        #self.set_state(state0)
        return self._get_obs()
    
    def _get_obs(self):
        theta, thetadot = self.state
        return np.array([theta+np.pi, thetadot])
        #return np.array([np.cos(theta), np.sin(theta), thetadot])

    def render(self, mode='human', close=False):
        if self.renderer is None:
            self.renderer = PendulumDraw(self)
            self.renderer.init_ui()
        self.renderer.update(*self.get_state(noisy=False))

    def close(self):
        if self.renderer is not None:
            self.renderer.close()


'''
class PendulumDraw(plant.PlantDraw):
    def __init__(self, pendulum_plant, refresh_period=(1.0/240),
                 name='PendulumDraw'):
        super(PendulumDraw, self).__init__(pendulum_plant,
                                           refresh_period, name)
        l = self.plant.l
        m = self.plant.m

        self.mass_r = 0.05*np.sqrt(m)  # distance to corner of bounding box

        self.center_x = 0
        self.center_y = 0

        # initialize the patches to draw the pendulum
        self.pole_line = plt.Line2D((self.center_x, 0), (self.center_y, l),
                                    lw=2, c='r')
        self.mass_circle = plt.Circle((0, l), self.mass_r, fc='y')

    def init_artists(self):
        self.ax.add_patch(self.mass_circle)
        self.ax.add_line(self.pole_line)

    def _update(self, state, t, *args, **kwargs):
        l = self.plant.l

        if self.plant.angle_dims:
            mass_x = l*state[2] + self.center_x
            mass_y = -l*state[3] + self.center_y
        else:
            mass_x = l*np.sin(state[0]) + self.center_x
            mass_y = -l*np.cos(state[0]) + self.center_y

        self.pole_line.set_xdata(np.array([self.center_x, mass_x]))
        self.pole_line.set_ydata(np.array([self.center_y, mass_y]))
        self.mass_circle.center = (mass_x, mass_y)

        return (self.pole_line, self.mass_circle)
'''

def angle_normalize(x):
    return (((x+np.pi) % (2*np.pi)) - np.pi)
