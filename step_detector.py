import math
from collections import deque

class StepDetector:
    # Dodałem parametr min_step_amplitude (wartość doświadczalna, zazwyczaj 0.5 - 2.0 m/s^2 w zależności od czułości)
    def __init__(self, norm_window_size=20, lp_filter_size=7, threshold_window_size=10, min_step_amplitude=0.8):
        self.norm_window_size = norm_window_size
        self.lp_filter_size = lp_filter_size
        self.threshold_window_size = threshold_window_size
        self.min_step_amplitude = min_step_amplitude  # NOWE: Minimalna siła kroku
        
        self.norm_buffer = deque([], norm_window_size) # Poprawiłem: maxlen w konstruktorze deque
        self.lp_filter_buffer = deque([0] * 7, lp_filter_size)
        self.threshold_buffer = deque([], threshold_window_size)
        
        self.last_filtered = 0
        self.last_slope = 0
        self.last_peak = 0
        self.peak_pair = [0, 0]

        self.step_count = 0

    def norm(self, ax, ay, az):
        return math.sqrt(ax**2 + ay**2 + az**2)
    
    def block_dc(self, sample, window):
        if not window: return 0 # Zabezpieczenie przed dzieleniem przez 0 na początku
        window_sum = sum(window)
        window_avg = window_sum / len(window)
        return sample - window_avg
    
    def lp_filter(self, buf):
        # Upewnij się, że bufor jest pełny zanim użyjesz stałych indeksów, 
        # w przeciwnym razie IndexError na początku działania
        if len(buf) < 7:
            return buf[-1] 
        y = (buf[0] + 2*buf[1] + 3*buf[2] + 4*buf[3] + 3*buf[4] + 2*buf[5] + buf[6]) / 16
        return y

    def sign_of_slope(self, last, current):
        return 1 if current > last else -1

    def process_sample(self, ax, ay, az):
        # Norm of acceleration vector
        new_sample = self.norm(ax, ay, az)
        self.norm_buffer.append(new_sample)

        # DC Blocking and Low-Pass Filtering
        dc_blocked_sample = self.block_dc(new_sample, self.norm_buffer)
        self.lp_filter_buffer.appendleft(dc_blocked_sample)
        
        # Oczekiwanie na wypełnienie bufora filtra
        if len(self.lp_filter_buffer) < self.lp_filter_size:
             return

        filtered_sample = self.lp_filter(self.lp_filter_buffer)

        # Slope of filtered signal
        slope = self.sign_of_slope(self.last_filtered, filtered_sample)

        # The average threshold of the filtered norm 
        self.threshold_buffer.append(filtered_sample)
        threshold = sum(self.threshold_buffer) / len(self.threshold_buffer)

        # Peak candidates
        peak_candidate  = None
        if slope == -1 and self.last_slope == 1:
            peak_candidate = 1 # maximum
        elif slope == 1 and self.last_slope == -1:
            peak_candidate = -1 # minimum

        # Bufor check
        if (len(self.norm_buffer) < self.norm_window_size) or (len(self.threshold_buffer) < self.threshold_window_size):
            self.last_filtered = filtered_sample
            self.last_slope = slope
            return

        if peak_candidate is not None:
            # Finding true local maximum or minimum
            if peak_candidate == 1 and self.last_peak == -1: # maximum comes after minimum
                # ZMIANA: Sprawdzamy czy sygnał przebił dynamiczny próg ORAZ czy jest silniejszy niż szum
                if filtered_sample > threshold and filtered_sample > self.min_step_amplitude:
                    self.peak_pair[0] = peak_candidate
                    self.last_peak = peak_candidate
            
            elif peak_candidate == -1 and self.last_peak == 1: # minimum comes after maximum
                # ZMIANA: Sprawdzamy czy sygnał jest poniżej progu ORAZ czy spadek jest znaczący
                if filtered_sample < threshold and filtered_sample < -self.min_step_amplitude:
                    self.peak_pair[1] = peak_candidate
                    self.last_peak = peak_candidate
            
            elif self.last_peak == 0:
                # Inicjalizacja pierwszego piku, też musi spełniać warunek amplitudy
                if peak_candidate == 1 and filtered_sample > self.min_step_amplitude:
                    self.last_peak = peak_candidate
                elif peak_candidate == -1 and filtered_sample < -self.min_step_amplitude:
                     self.last_peak = peak_candidate

            # Pair of local maximum and minimum found = step detected
            if self.peak_pair[0] * self.peak_pair[1] == -1:
                print(f"STEP! Amplitude: {filtered_sample:.4f}")
                self.step_count += 1
                self.peak_pair = [0, 0]
        
        self.last_filtered = filtered_sample
        self.last_slope = slope

    def get_step_count(self):
        return self.step_count
    
    def reset(self):
        self.norm_buffer.clear()
        self.lp_filter_buffer = deque([0] * 7, maxlen=7)
        self.threshold_buffer.clear()
        
        self.last_filtered = 0
        self.last_slope = 0
        self.last_peak = 0
        self.peak_pair = [0, 0]

        self.step_count = 0
        
    def reset_step_count(self):
        self.step_count = 0
        
    def add_step(self):
        self.step_count += 1
