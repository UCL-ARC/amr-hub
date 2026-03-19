import logging
import time
from amr_hub_abm.run import simulate

logging.basicConfig(level=logging.WARNING)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if __name__ == "__main__":
    time_start = time.perf_counter()
    simulate(plot=False, record=False, plot_trajectory=False)
    time_end = time.perf_counter()
    logger.info("Simulation run time: %s seconds", time_end - time_start)
