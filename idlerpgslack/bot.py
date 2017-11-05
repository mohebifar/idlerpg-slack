import copy
import time
import logging

from api import SlackApiClient
import db

READ_EVENT_PAUSE = .1

class IdleRpgBot():
    """A Slack bot for playing IdleRPG. An IdleRPG Slack bot will track the
    time users are active in the rpg channel, and will respond to commands.
    """

    def __init__(self, slack_token, rpg_channel_name, db_filename):
        """Return an IdleRPG Slack bot

        Args:
            slack_token: The token used to authenticate with Slack
            rpg_channel_name: The name of the Slack channel used to play IdleRPG
        """
        self._api = SlackApiClient(slack_token)
        self._name = None
        self._id = None
        self._rpg_channel_id = None
        self._rpg_channel_name = rpg_channel_name
        self._db_filename = db_filename
        self._users = {}

        self.load()

    def connect(self):
        """Initiate a connection with Slack"""
        self._api.connect()
        self._post_connection_init()

        while True:
            events = self._api.read()

            for event in events:
                self._handle_event(event)
            time.sleep(READ_EVENT_PAUSE)

    def save(self):
        """Save the current user information to disk

        A clone is created of the user copy before saving, so that all users
        can be set to offline before being saved to disk
        """
        current_users = copy.deepcopy(self._users)
        for user_id, user in current_users.items():
            if user['active']:
                set_offline(current_users, user_id)

        db.save(self._db_filename, current_users)
        logging.debug('Users saved to {}'.format(self._db_filename))

    def load(self):
        """Load user information from disk"""
        self._users = db.load(self._db_filename)
        logging.debug('Users loaded from {}'.format(self._db_filename))

    def _post_connection_init(self):
        self_user = self._api.get_self()

        self._name = self_user['name']
        self._id = self_user['id']

        rpg_channel = self._api.get_channel(self._rpg_channel_name)
        self._rpg_channel_id = rpg_channel['id']
        self._update_all_users()

    def _update_user(self, user_id):
        if not user_id in self._users:
            user = self._api.get_user_info(user_id)

            if user['is_bot']:
                return

            self._users[user_id] = {
                'profile': user['profile'],
                'active': False,
                'first_seen': None,
                'total': 0
            }

        active = self._api.is_user_active(user_id)

        if active:
            if not self._users[user_id]['active']:
                set_online(self._users, user_id)

        else:
            if self._users[user_id]['active']:
                set_offline(self._users, user_id)

    def _handle_event(self, event):
        logging.debug('Recieved event: {}'.format(event))
        if event['type'] == 'message':
            self._handle_message(event)
        elif event['type'] == 'presence_change':
            self._handle_presence_change(event)

    def _handle_message(self, event):
        text = event['text']
        if text.startswith('<@{}>'.format(self._id)):
            chunks = text.split()

            if len(chunks) > 1:
                args = []
                if len(chunks) > 2:
                    args = chunks[2:]
                self._handle_command(event, chunks[1], args)

    def _handle_command(self, event, command, args):
        if command.lower() == 'hello' or command.lower() == 'hi':
            self._hello(event['channel'])
        elif command.lower() == 'scores':
            scores = []
            for user_id, user in self._users.items():
                name = user['profile']['display_name']
                if len(name) == 0:
                    name = user['profile']['real_name']
                if len(name) == 0:
                    name = user['profile']['email']

                total = user['total']

                if user['active']:
                    total += time.time() - user['first_seen']
                scores.append('{}: {}'.format(name, total))
            self._api.send_message(event['channel'], 'Scores:\n{}'.format('\n'.join(scores)))
        elif command.lower() == 'save':
            self.save()
        elif command.lower() == 'load':
            self.load()
            self._update_all_users()

    def _update_all_users(self):
        member_ids = self._api.get_channel_users(self._rpg_channel_id)

        for member_id in member_ids:
            self._update_user(member_id)


    def _handle_presence_change(self, event):
        self._update_user(event['user'])

    def _hello(self, channel_id):
        self._api.send_message(channel_id, 'Hello from Python! :tada:')

def set_online(users, user_id):
    users[user_id]['active'] = True
    users[user_id]['first_seen'] = time.time()

def set_offline(users, user_id):
    users[user_id]['active'] = False
    users[user_id]['total'] += time.time() - users[user_id]['first_seen']
    users[user_id]['first_seen'] = None