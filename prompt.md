create a new python project called webex-terminal that will allow a user to join cisco webex rooms from terminal windows and interact with the room. The goals are the following:

1) Allow a user to start a webex session from the terminal. This will initiate an oauth2 session, and once authenticated, the token will be stored so that it can be used in multiple sessions.
2) Once the session has been established, a user can join a room in each terminal.
3) A user can only join one room in each terminal, so issuing a join in one terminal will result is not listening in the previous room
4) The active room monitor should listen to the webex service using websockets and not webhooks