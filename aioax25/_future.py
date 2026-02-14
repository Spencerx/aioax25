#!/usr/bin/env python3

"""
Future wrapping routines
"""


class FutureWrapperMixin(object):
    """
    Helper mix-in class that optionally wraps a future.
    """

    def _ensure_future(self, future):
        """
        Ensure the a future is passed through or created as required:
        - if we're given a `Future`, pass it through as-is.
        - if not, and return_future was set to `True`; create one and return
          it.
        - otherwise, we're operating in the legacy one-shot mode, do nothing.
        """
        if future is not None:
            # We're given a future, pass it through
            return future
        elif self._return_future:
            # We are always expected to return a future, do so
            return self._loop.create_future()
        else:
            # We're being used in one-shot mode
            return None

    def _future_ready(self, f):
        """
        Return true if the future is ready to take a result.
        """
        return (f is not None) and (not f.done())
