from sqlalchemy.orm.exc import NoResultFound
from celery import Celery
import arrow

from FlowrouteMessagingLib.Controllers.APIController import APIController
from FlowrouteMessagingLib.Models.Message import Message

from appointment_reminder.settings import (
    FLOWROUTE_ACCESS_KEY, FLOWROUTE_SECRET_KEY, FLOWROUTE_NUMBER,
    MSG_TEMPLATE, ORG_NAME)
from appointment_reminder.models import Reminder
from appointment_reminder.log import log
from appointment_reminder.service import reminder_app

sms_controller = APIController(username=FLOWROUTE_ACCESS_KEY,
                               password=FLOWROUTE_SECRET_KEY)


def new_celery(app=reminder_app):
    celery = Celery(app.import_name)
    celery.conf.update(app.config)
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask
    return celery

celery = new_celery()


def create_message_body(appt):
    appt_context = ''
    if appt.location:
        appt_context += ' at {}'.format(appt.location)
    if appt.participant:
        appt_context += ' with {}'.format(appt.participant)
    msg = MSG_TEMPLATE.format(
        ORG_NAME,
        arrow.get(appt.appt_user_dt).strftime("%A, %b %d %I:%M %p"),
        appt_context)
    return msg


@celery.task()
def send_reminder(reminder_id):
    """
    """
    try:
        appt = Reminder.query.filter_by(id=reminder_id).one()
    except NoResultFound:
        log.error({"message": "Received unknown appointment id {}.".format(
            reminder_id), "reminder_id": reminder_id})
        return
    msg_body = create_message_body(appt)
    message = Message(
        to=appt.contact_num,
        from_=FLOWROUTE_NUMBER,
        content=msg_body)
    try:
        sms_controller.create_message(message)
    except Exception as e:
        strerr = vars(e).get('response_body', None)
        log.critical({"message": "Raised an exception sending SMS",
                      "exc": e, "strerr": strerr, "reminder_id": reminder_id})
    else:
        log.info(
            {"message": "Message sent to {} for reminder {}".format(
             appt.contact_num, reminder_id),
             "reminder_id": reminder_id})
