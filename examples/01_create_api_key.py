from pytakeoff import TakeoffClient

with TakeoffClient() as client:                  # key read from your saved credentials
    project = client.projects.create("draft",force=True)      # new project, made current
