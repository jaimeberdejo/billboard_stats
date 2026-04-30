# Quick Task Plan

Improve the `Most Simultaneous Entries` drilldown UX and data shape.

Steps:

1. Move artist drilldown rendering inline so expanded content appears directly under the clicked artist row.
2. Extend the simultaneous-entry drilldown data model to return every qualifying chart week for the selected artist.
3. Group each artist's simultaneous weeks by chart date and render the full set of entries for each week inline.
4. Verify the updated records UI and records query helpers with lint and TypeScript.
