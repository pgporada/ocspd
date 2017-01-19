"""
This module defines a context in which we can run actions that are likely to
fail because they have intricate dependencies e.g. network connections,
file access, parsing certificates and validating their chains, etc., without
stopping execution of the application. Additionally it will log these errors
and depending on the nature of the error reschedule the task at a time that
seems reasonable, i.e.: we can reasonably expect the issue to be resolved by
that time.

It is generally considered bad practice to catch all remaining exceptions,
however this is a daemon. We can't afford it to get stuck or crashed. So in the
interest of staying alive, if an exception is not caught specifically, the
handler will catch it, generate a stack trace and save if in a file in the
current working directory. A log entry will be created explaining that there
was an exception, inform about the location of the stack trace dump and that
the context will be dropped. It will also kindly request the administrator to
contact the developers so the exception can be caught in a future relaese which
will probably increase stability and might result in a retry rather than just
droppingt the context.

Dropping the context effectively means that a retry won't occur and since the
context will have no more references, it will be garbage collected.
There is however still a reference to the certificate model in
:attr:`core.daemon.run.models`. With no scheduled actions it will
just sit idle, until the finder detects that it is either removed – which will
cause the entry in :attr:`core.daemon.run.models` to be deleted, or
it is changed. If the certificate file is changed the finder will schedule
schedule a parsing action for it and it will be picked up again. Hopefully the
issue that caused the uncaught exception will be resolved, if not, if will be
caught again and the cycle continues.
"""

from contextlib import contextmanager
import datetime
import logging
import os
import traceback
import urllib.error
import requests.exceptions
from core.exceptions import OCSPBadResponse
from core.exceptions import RenewalRequirementMissing
from core.exceptions import CertFileAccessError
from core.exceptions import CertParsingError
from core.exceptions import CertValidationError
from core.exceptions import OCSPRenewError

LOG = logging.getLogger()
STACK_TRACE_FILENAME = "ocspd_exception{:%Y%m%d-%H%M%s%f}.trace"


@contextmanager
def ocsp_except_handle(ctx=None):
    """
    Handle lots of potential errors and reschedule failed action contexts.
    """
    # pylint: disable=broad-except
    try:
        yield  # do the "with ocsp_except_handle(ctx):" code block
    except CertFileAccessError as exc:
        # Can't access the certificat file, we can try again a bit later..
        err_count = ctx.set_last_exception(str(exc))
        if err_count < 4:
            LOG.error(exc)
            ctx.reschedule(60 * err_count)
        elif err_count < 7:
            ctx.reschedule(err_count * 3600)
        else:
            LOG.critical("{}, giving up..".format(exc))
    except OCSPBadResponse as exc:
        LOG.error(exc)
    except OCSPRenewError as exc:
        LOG.critical(exc)
    except (RenewalRequirementMissing,
            CertValidationError,
            CertParsingError) as exc:
        # Can't parse or validate the certificat file, or a requirement for
        # OCSP renewal is missing.
        # We can't do anything until the certificate file is changed which
        # means we should not rechedule, when the certificate file changes,
        # the certfinder will add it to the parsing queue anyway..
        LOG.critical(exc)
    except urllib.error.URLError as err:
        LOG.error("Connection problem: %s", err)
    except (requests.Timeout,
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ReadTimeout) as err:
        LOG.warning("Timeout error for %s: %s", ctx.model.filename, exc)
    except requests.exceptions.TooManyRedirects as err:
        LOG.warning(
            "Too many redirects for %s: %s", ctx.model.filename, exc)
    except requests.exceptions.HTTPError as exc:
        LOG.warning(
            "Received bad HTTP status code \%\s from OCSP server \%\s for "
            " %s: %s",
            # status,
            # url,
            ctx.model.filename,
            exc
        )
    except (requests.ConnectionError,
            requests.RequestException) as err:
        LOG.warning("Connection error for %s: %s", ctx.model.filename, err)

        # if context.model.url_index > len(self.ocsp_urls):
        # No more urls to try
    except Exception as exc:  # the show must go on..
        dump_stack_trace(ctx, exc)

# action_ctx.reschedule(3600)


def delete_ocsp_for_context(ctx):
    """
    When something bad happens, sometimes it is good to delete a related bad
    OCSP file so it can't be served any more.

    TODO: Check that HAProxy doesn't cache this, it probably does, we need to
    be able to tell it not to remember it.
    """
    LOG.info("Deleting any OCSP staple: \"%s.ocsp\" if it exists.", ctx.model)
    try:
        ocsp_file = "{}.ocsp".format(ctx.model)
        os.remove(ocsp_file)
    except IOError:
        LOG.debug(
            "Can't delete OCSP staple %s, maybe it doesn't exist.",
            ocsp_file
        )


def dump_stack_trace(ctx, exc):
    """
    Examine the last exception and dump a stack trace to a file, if it fails
    due to an IOError or OSError, log that it failed so the a sysadmin
    may make the directory writeable.
    """
    trace_file = STACK_TRACE_FILENAME.format(datetime.datetime.now())
    trace_file = os.path.join(os.getcwd(), trace_file)
    try:
        with open(trace_file, "w") as file_handle:
            traceback.print_exc(file=file_handle)
        LOG.critical(
            "Prevented thread from being killed by uncaught exception: %s\n"
            "Context %s will be dropped as a result of the exception.\n"
            "A stack trace has been saved in %s\n"
            "Please report this error to the developers so the exception can "
            "be handled in a future release, thank you!",
            exc,
            ctx,
            trace_file
        )
    except (IOError, OSError) as trace_exc:
        LOG.critical(
            "Prevented thread from being killed by uncaught exception: %s\n"
            "Context %s will be dropped as a result of the exception.\n"
            "Couldn't dump stack trace to: %s reason: %s\n"
            "Please report this error to the developers so the exception can "
            "be handled in a future release, thank you!",
            exc,
            ctx,
            trace_file,
            trace_exc
        )
