"""
This module defines an extended version of the general purpose
:class:`scheduling.ScheduledTaskContext` for use in the OCSP daemon.
"""
from scheduling import ScheduledTaskContext


class OCSPTaskContext(ScheduledTaskContext):
    """
    Adds the following functionality to the
    :class:`scheduling.ScheduledTaskContext`:

     - Keep track of the exception that occurred last, and how many times it
       occurred.
    """
    def __init__(self, task_name, model, sched_time=None, **attributes):
        """
        Initialise a OCSPTaskContext with a cert model, optional scheduled time
        and task name.

        :param str task_name: A task namecorresponding to an existing queue in
            the scheduler.
        :param core.certmodel.CertModel model: A certificate model.
        :param datetime.datetime|int sched_time: Absolute time
            (datetime.datetime object) or relative time in seconds (int) to
            execute the task or None for processing ASAP.
        :param kwargs attributes: Any data you want to assign to the context,
            avoid using names already defined in the context: scheduler, task,
            name, sched_time, reschedule.
        """
        self.last_exception = None
        self.last_exception_count = 0

        super(OCSPTaskContext, self).__init__(
            task_name=task_name,
            subject=model,
            sched_time=sched_time,
            **attributes
        )
        self.model = self.subject

    def set_last_exception(self, exc):
        """
        Set the exception that occurred just now, this function will return
        the amount of times the same exception has occurred in a row.
        :param str exc: The last exception as a string.
        :return int: Count of same exceptions in a row.
        """
        if not self.last_exception or repr(self.last_exception) is repr(exc):
            self.last_exception = exc
            self.last_exception_count = 1
        else:
            self.last_exception_count += 1
        return self.last_exception_count
