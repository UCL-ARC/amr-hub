import time
from amr_hub_abm.run import simulate


if __name__ == "__main__":
    time_start = time.time()
    simulate(plot=False, record=True)
    time_end = time.time()
    print(f"Simulation run time: {time_end - time_start} seconds")
