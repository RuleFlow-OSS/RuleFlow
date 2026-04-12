from matplotlib import use
import cellpylib as cpl

def run_example():
    use('WebAgg')
    cellular_automaton = cpl.init_simple2d(60, 60)
    cellular_automaton[:, [28,29,30,30], [30,31,29,31]] = 1
    cellular_automaton[:, [40,40,40], [15,16,17]] = 1
    cellular_automaton[:, [18,18,19,20,21,21,21,21,20], [45,48,44,44,44,45,46,47,48]] = 1
    cellular_automaton = cpl.evolve2d(cellular_automaton, timesteps=60, neighbourhood='Moore',
                                      apply_rule=cpl.game_of_life_rule, memoize='recursive')
    cpl.plot2d_animate(cellular_automaton)
