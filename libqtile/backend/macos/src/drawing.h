#ifndef MAC_DRAWING_H
#define MAC_DRAWING_H

#include <stdbool.h>
#include <stddef.h>

struct mac_internal {
    void *win;  // NSWindow, owned by the native drawing object.
    void *view; // NSView, owned by the native drawing object.
    int width;
    int height;
    void *buffer; // Borrowed pixel storage owned by the native object.
};

// Creates and owns an AppKit window, view, and pixel buffer. Returns NULL on
// allocation or AppKit initialization failure.
struct mac_internal *mac_internal_new(int x, int y, int width, int height);

// Releases all native resources. No field or buffer pointer may be used after
// this call returns.
void mac_internal_free(struct mac_internal *internal);
void mac_internal_place(struct mac_internal *internal, int x, int y, int width, int height);

// Returns a borrowed pointer valid until mac_internal_free or replacement of
// the backing surface. Python must not release this pointer directly.
void *mac_internal_get_buffer(struct mac_internal *internal);
void mac_internal_draw(struct mac_internal *internal);
void mac_internal_set_visible(struct mac_internal *internal, bool visible);
void mac_internal_bring_to_front(struct mac_internal *internal);

#endif
