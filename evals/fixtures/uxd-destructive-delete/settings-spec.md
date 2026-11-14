# Workspace Settings page (current)

## Layout
Single form with fields: Workspace name, Timezone, Default language.
At the bottom, a right-aligned button row:

    [ Delete workspace ]  [ Save changes ]

Both buttons use the primary style (filled, brand blue, same size).
"Delete workspace" is visible to every admin.

## Delete confirmation
Clicking "Delete workspace" opens a modal:

    Are you sure?
    [ Cancel ]  [ OK ]

- OK is focused by default, so pressing Enter confirms.
- The modal is a `<div>` overlay; focus is not moved into it and Tab moves
  through the page behind it.
- Deletion is immediate and permanent: all projects, files, and members are
  removed.

## Data
- Support receives about 3 tickets per week from admins who deleted a
  workspace by accident, usually right after editing settings.
- Restoring requires an engineer to replay backups (about 6 hours of work each).

## Brand team request (separate)
"Please make every primary button our new red (#E0245E) to match the
campaign."
