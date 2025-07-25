from c_is import country_indicators
from p_ss import pair_scores
from p_t_s import pair_total_score

import time

while True:
    country_indicators.run()
    pair_scores.run()
    pair_total_score.run()
    print("done. sleep.")
    time.sleep(3600)  # Sleep for 1 minute before next run

