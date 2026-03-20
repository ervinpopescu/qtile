#include "display.h"
#import <AppKit/NSApplication.h>
#import <AppKit/NSScreen.h>
#import <ApplicationServices/ApplicationServices.h>
#import <Foundation/Foundation.h>
#import <IOKit/pwr_mgt/IOPMLib.h>

void mac_init_app(void) {
    // NSApplication must exist before creating any NSWindow.
    // Accessory policy: no dock icon, no main menu bar — qtile is a background
    // window-management process, not a regular GUI app.
    [NSApplication sharedApplication];
    [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
}

static IOPMAssertionID g_idle_assertion = kIOPMNullAssertionID;

void mac_inhibit_idle(bool inhibit) {
    if (inhibit && g_idle_assertion == kIOPMNullAssertionID) {
        // Prevent display sleep and system idle sleep while qtile inhibits idle.
        IOPMAssertionCreateWithName(kIOPMAssertionTypeNoDisplaySleep, kIOPMAssertionLevelOn,
                                    CFSTR("qtile idle inhibitor"), &g_idle_assertion);
    } else if (!inhibit && g_idle_assertion != kIOPMNullAssertionID) {
        IOPMAssertionRelease(g_idle_assertion);
        g_idle_assertion = kIOPMNullAssertionID;
    }
}

int mac_get_outputs(struct mac_output **outputs, size_t *count) {
    uint32_t displayCount = 0;
    if (CGGetActiveDisplayList(0, NULL, &displayCount) != kCGErrorSuccess)
        return 1;

    CGDirectDisplayID *displays = malloc(sizeof(CGDirectDisplayID) * displayCount);
    if (!displays) {
        return 1;
    }
    CGGetActiveDisplayList(displayCount, displays, &displayCount);

    *count = displayCount;
    *outputs = malloc(sizeof(struct mac_output) * displayCount);
    if (!*outputs) {
        free(displays);
        return 1;
    }

    for (uint32_t i = 0; i < displayCount; i++) {
        // We need the usable area excluding the macOS system menu bar (and Dock,
        // if visible).  NSScreen.visibleFrame gives us this in AppKit coordinates
        // (origin at bottom-left, Y-up), so we convert to CG coordinates
        // (origin at top-left, Y-down) which qtile uses internally.
        //
        // Fall back to CGDisplayBounds if no matching NSScreen is found.
        CGRect fullBounds = CGDisplayBounds(displays[i]);
        CGRect usable = fullBounds;

        // Match CGDirectDisplayID to NSScreen via CGDirectDisplayID.
        for (NSScreen *screen in [NSScreen screens]) {
            NSDictionary *desc = [screen deviceDescription];
            CGDirectDisplayID screenID = [[desc objectForKey:@"NSScreenNumber"] unsignedIntValue];
            if (screenID == displays[i]) {
                NSRect visible = [screen visibleFrame];
                NSRect full = [screen frame];
                // Convert AppKit coords (bottom-left origin) to CG coords
                // (top-left origin).  The CG Y of the visible area's top edge
                // equals fullBounds.origin.y + (full.height - (visible.origin.y
                // - full.origin.y + visible.height)).
                double cgY =
                    fullBounds.origin.y +
                    (full.size.height - (visible.origin.y - full.origin.y + visible.size.height));
                usable = CGRectMake(fullBounds.origin.x + (visible.origin.x - full.origin.x), cgY,
                                    visible.size.width, visible.size.height);
                break;
            }
        }

        (*outputs)[i].x = (int)usable.origin.x;
        (*outputs)[i].y = (int)usable.origin.y;
        (*outputs)[i].width = (int)usable.size.width;
        (*outputs)[i].height = (int)usable.size.height;

        // Use CGDisplayUnitNumber to produce a stable, hardware-tied name
        // that survives display reconnections and enumeration-order changes,
        // unlike a loop index which shifts when displays are added or removed.
        char buf[32];
        snprintf(buf, sizeof(buf), "display-%u", CGDisplayUnitNumber(displays[i]));
        (*outputs)[i].name = strdup(buf);
    }

    free(displays);
    return 0;
}

void mac_free_outputs(struct mac_output *outputs, size_t count) {
    for (size_t i = 0; i < count; i++) {
        free(outputs[i].name);
    }
    free(outputs);
}

void mac_get_mouse_position(int *x, int *y) {
    CGEventRef event = CGEventCreate(NULL);
    if (!event) {
        *x = 0;
        *y = 0;
        return;
    }
    CGPoint point = CGEventGetLocation(event);
    CFRelease(event);
    *x = (int)point.x;
    *y = (int)point.y;
}

void mac_warp_pointer(int x, int y) {
    CGPoint point = CGPointMake(x, y);
    CGWarpMouseCursorPosition(point);
}

void mac_poll_runloop(void) { CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0, true); }

void mac_simulate_keypress(uint32_t keycode, uint64_t flags) {
    CGEventSourceRef source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState);
    if (!source)
        return;

    CGEventRef down = CGEventCreateKeyboardEvent(source, (CGKeyCode)keycode, true);
    if (down) {
        CGEventSetFlags(down, (CGEventFlags)flags);
        CGEventPost(kCGHIDEventTap, down);
        CFRelease(down);
    }

    CGEventRef up = CGEventCreateKeyboardEvent(source, (CGKeyCode)keycode, false);
    if (up) {
        CGEventSetFlags(up, (CGEventFlags)flags);
        CGEventPost(kCGHIDEventTap, up);
        CFRelease(up);
    }

    CFRelease(source);
}
