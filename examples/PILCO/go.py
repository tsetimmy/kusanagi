import numpy as np
import gym

env = gym.make('Pendulum-v0')




while True:
    state = env.reset()

    time_steps = 0
    while True:

        time_steps += 1
        action = env.action_space.sample()

        next_state, reward, done, _ = env.step(action)
       

        print (reward)
        state = next_state.copy()

        if done:
            break

    print ('here is the ep tim_steps', time_steps)


