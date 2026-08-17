.. _macos_backend:

=================
macOS backend
=================

This page is for contributors working on Qtile's macOS backend. It describes
how the Python backend calls the native Objective-C implementation through
CFFI, and is not a stable public API for Qtile configuration files.

.. note::

   The CFFI layer is an internal backend ABI. Its names and ownership rules may
   change while the backend is being developed. The Python classes in
   ``libqtile.backend.macos`` are the Qtile-facing layer.

Architecture
============

The backend is split into a Python layer, a CFFI boundary, and a native macOS
layer::

    Python backend wrappers
            |
    libqtile.backend.macos._ffi
            |
    CFFI declarations in cffi/build.py
            |
    Objective-C headers and implementations in src/
            |
    AppKit, Accessibility, Core Graphics, Quartz Events, and IOKit

The extension exposes ``ffi`` for allocating and converting C values and
``lib`` for calling native functions::

    from libqtile.backend.macos import _ffi

    ffi = _ffi.ffi
    lib = _ffi.lib

Design goals
============

The backend is designed around a small native boundary and a large Python
policy layer. The native layer should provide macOS primitives, while Python
should continue to own Qtile concepts such as groups, layouts, floating state,
configuration, hooks, and commands.

The main goals are:

* keep macOS framework details isolated from the rest of Qtile;
* expose a small, explicit CFFI contract instead of leaking Objective-C types;
* make ownership, callbacks, and failure behavior visible at the boundary;
* keep the Python wrappers testable with a fake FFI implementation; and
* allow each native subsystem to be replaced or extended without changing
  unrelated backend code.

The backend is intentionally not a general-purpose macOS window-management
library. Its native API exists to support Qtile's backend interfaces.

Subsystem boundaries
====================

Display and run loop
--------------------

The display layer translates display enumeration, pointer operations, and the
Core Foundation run loop into plain C values. It must not contain Qtile policy.
The Python ``Core`` object owns scheduling and decides when to poll the run
loop.

Window management
-----------------

The window manager uses macOS Accessibility objects internally, but exposes
opaque ``mac_window`` values through CFFI. It owns the conversion between
Accessibility attributes and simple C values. The Python ``Window`` wrapper
translates those values into Qtile's window interface.

Input and observers
-------------------

The event tap and Accessibility observer are callback-based native services.
The Python ``Core`` object owns callback handles, translates notifications into
Qtile events, and stops both services during finalization.

Drawing
-------

The drawing layer owns AppKit windows, views, and pixel buffers. Python owns
surface preparation and drawing policy, while Objective-C owns AppKit object
creation and presentation. A buffer returned by ``mac_internal_get_buffer`` is
borrowed and must never outlive its native drawing object.

Lifecycle
=========

A normal backend lifecycle is:

#. Initialise the AppKit process state before creating AppKit objects.
#. Create the native ``Core`` services and retain callback handles.
#. Enumerate outputs and windows, wrapping native values in Python objects.
#. Poll the run loop while translating callbacks into Qtile events.
#. Stop observers and event taps before releasing callback handles.
#. Release windows, drawing objects, output arrays, and allocated strings.

Shutdown ordering is part of the API contract. In particular, callbacks must
be stopped before their Python callback objects are collected, and native
objects must be released before their borrowed pointers are discarded.

Reviewing a backend change
==========================

For a change to the macOS backend, review the following questions before
accepting the implementation:

* Does the change belong in the native primitive layer or the Python policy
  layer?
* Does it introduce an Objective-C type across the CFFI boundary unnecessarily?
* Who allocates, owns, and releases each pointer or returned string?
* What happens when Accessibility permission is unavailable?
* What happens when a macOS API returns an error or ``NULL``?
* Which thread or run loop invokes callbacks?
* Can the behavior be tested with the fake FFI on Linux?
* Are the declarations in ``cffi/build.py`` and ``src/*.h`` synchronized?
* Does shutdown remain safe if initialization only partially completed?
* Does the change preserve the corresponding Qtile backend abstraction?

A reviewer should be able to disagree with a design decision from this page,
then propose a different boundary or lifecycle rule without first reverse
engineering the implementation.

Source map
==========

The most useful files to read in order are:

* ``libqtile/backend/macos/cffi/build.py`` - defines the Python-facing CFFI
  declarations and compiles the native objects.
* ``libqtile/backend/macos/src/display.h`` and ``display.m`` - displays,
  pointer movement, the run loop, and idle inhibition.
* ``libqtile/backend/macos/src/window_manager.h`` and ``window_manager.m`` -
  Accessibility-backed window discovery and window operations.
* ``libqtile/backend/macos/src/event_tap.h`` and ``event_tap.m`` - keyboard
  event taps and idle-time queries.
* ``libqtile/backend/macos/src/drawing.h`` and ``drawing.m`` - native windows
  used by drawers and their pixel buffers.
* ``libqtile/backend/macos/core.py`` and ``window.py`` - Python wrappers that
  translate the native API into Qtile backend objects.

CFFI API groups
===============

Displays and pointer handling
-----------------------------

``mac_get_outputs`` returns an allocated array of ``mac_output`` structures.
The caller must release it with ``mac_free_outputs``. Output coordinates and
pointer coordinates use the global Quartz coordinate space.

``mac_get_mouse_position`` and ``mac_warp_pointer`` read and change the global
pointer position. ``mac_poll_runloop`` processes pending Core Foundation and
Accessibility callbacks and is called periodically by the Python backend.

Windows and Accessibility
-------------------------

``mac_window`` contains an opaque ``AXUIElementRef`` pointer and Qtile's stable
window identifier. The pointer is not safe to use after the native object has
been released.

The window API covers:

* enumeration with ``mac_get_windows`` and ``mac_free_windows``;
* focused-window lookup with ``mac_get_focused_window``;
* metadata such as title, role, application name, and bundle identifier;
* geometry, focus, stacking, visibility, and process identification; and
* fullscreen, maximized, minimized, parent, and kill operations.

Window structures returned by native code own an Accessibility reference.
Retain a structure when storing it beyond the immediate operation and release
it when the Python wrapper is finished with it. Returned C strings are newly
allocated and must be released with ``free`` after conversion to Python.

The window observer uses ``ax_observer_cb``. Keep the CFFI callback object alive
for as long as the observer is running, and call ``mac_observer_stop`` before
releasing it.

Event taps and idle
-------------------

``mac_event_tap_start`` installs a Quartz event tap and calls an
``event_tap_cb`` callback with the event type, the full 64-bit modifier flags,
and the keycode. Stop the tap with ``mac_event_tap_stop`` before discarding the
callback object.

``mac_get_idle_time`` reports the system idle time. ``mac_inhibit_idle``
controls the backend's idle-inhibition state.

Internal drawing
----------------

``mac_internal_new`` creates an AppKit-backed native window. The structure
contains opaque ``NSWindow`` and ``NSView`` pointers plus the dimensions and a
pixel buffer. ``mac_internal_get_buffer`` returns a borrowed pointer owned by
the native drawing object. Do not retain it after ``mac_internal_free`` or use
it after the drawing object has been replaced.

Call ``mac_internal_draw`` after changing the buffer. Use
``mac_internal_set_visible`` and ``mac_internal_bring_to_front`` for window
state changes, and always pair ``mac_internal_new`` with
``mac_internal_free``.

Contract rules
==============

When adding or changing an entry point, document these properties in the
native header and in the Python wrapper:

* who allocates and frees every pointer;
* whether an output is borrowed, retained, or transferred;
* what ``0``, non-zero values, ``NULL``, and empty arrays mean;
* which coordinate system is used;
* which thread or run loop invokes callbacks;
* how long callbacks, strings, and pixel buffers remain valid; and
* whether macOS Accessibility permission is required.

The declarations in ``cffi/build.py`` and ``src/*.h`` must remain synchronized.
The CFFI declarations are what Python sees, while the headers describe the
native implementation boundary.

Building and testing
====================

The native extension can only be built on macOS because it links against Apple
frameworks. From the repository root, run::

    python libqtile/backend/macos/cffi/build.py

For a debug build with symbols and reduced optimization, run::

    python libqtile/backend/macos/cffi/build.py --debug

The command compiles the Objective-C sources and generates the private
``libqtile.backend.macos._ffi`` extension. Native tests require macOS and
Accessibility permission. Unit tests using the fake FFI implementation can be
run on other platforms with::

    uv run pytest test/backend/macos/test_unit_*.py --noconftest -q --tb=short

Accessibility permission
=========================

Window enumeration and event observation use macOS Accessibility APIs. When
Qtile cannot see windows, check **System Settings -> Privacy & Security ->
Accessibility** and grant permission to the application launching Qtile.

External references
===================

CFFI
----

* `CFFI overview <https://cffi.readthedocs.io/en/latest/overview.html>`_
* `Out-of-line API mode <https://cffi.readthedocs.io/en/latest/using.html#out-of-line-api-mode>`_
* `CFFI callbacks <https://cffi.readthedocs.io/en/latest/using.html#callbacks>`_

Apple frameworks
----------------

* `Accessibility and AXUIElement <https://developer.apple.com/documentation/applicationservices/axuielement>`_
* `AXUIElement.h reference <https://developer.apple.com/documentation/applicationservices/axuielement_h>`_
* `Quartz Event Services <https://developer.apple.com/documentation/coregraphics/quartz-event-services>`_
* `CGEventTapCreate <https://developer.apple.com/documentation/coregraphics/cgevent/tapcreate>`_
* `CGEventFlags <https://developer.apple.com/documentation/coregraphics/cgeventflags>`_
* `NSWindow <https://developer.apple.com/documentation/appkit/nswindow>`_
* `NSView <https://developer.apple.com/documentation/appkit/nsview>`_
* `Core Graphics Display Services <https://developer.apple.com/documentation/coregraphics/display_services>`

Related Qtile code
------------------

* `macOS backend source <https://github.com/qtile/qtile/tree/master/libqtile/backend/macos>`_
* `CFFI build script <https://github.com/qtile/qtile/blob/master/libqtile/backend/macos/cffi/build.py>`_
* `Qtile contribution guide <https://docs.qtile.org/en/latest/manual/contributing.html>`_
