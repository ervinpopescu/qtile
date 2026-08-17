#include <stdbool.h>
#include <stdint.h>

// The callback runs from the event-tap/run-loop path. flags is uint64_t so
// that no CGEventFlags bits are truncated before Python receives them.
typedef int (*event_tap_cb)(uint32_t type, uint64_t flags, uint32_t keycode, void *userdata);

// The callback must remain alive until mac_event_tap_stop has returned.
// Returns 0 when the tap is installed and non-zero on failure.
int mac_event_tap_start(event_tap_cb callback, void *userdata);
void mac_event_tap_stop(void);

double mac_get_idle_time(void);
