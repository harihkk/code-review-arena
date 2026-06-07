# Changelog

All notable changes to this project are recorded here. The format follows the
Keep a Changelog conventions, and the project has not cut a tagged release yet.

## Unreleased

### Changed

- Reworked the audit report page into compact case-study cards and laid the
  detection versus validation gap out as a grid instead of stacked full-width rows.
- Compacted the leaderboard so it fits the page without horizontal scrolling and
  keeps each reviewer on a single line.
- Collapsed the cases table into one requirements column, with the full validator
  names tucked behind an expandable summary.
- Widened the content area and let the documentation index fill the page at three
  cards per row.
- Reviewer names now read as plain labels such as "Control: Perfect Repair" across
  the dashboard, and the control-baseline note appears wherever controls are shown.

### Removed

- Dropped the duplicate control tag that sat next to reviewer names, since the name
  already says it is a control.
- Removed reviewer helper functions that were no longer referenced.
