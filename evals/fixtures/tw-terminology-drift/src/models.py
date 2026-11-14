class Workspace:
    """Top-level customer container: members, billing, projects."""

    def __init__(self, name):
        self.name = name
        self.members = []
        self.projects = []


class Project:
    """A collection of tasks inside a workspace."""

    def __init__(self, workspace, name):
        self.workspace = workspace
        self.name = name
        self.archived = False
