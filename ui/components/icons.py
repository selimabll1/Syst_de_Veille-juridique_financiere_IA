"""Small inline vector icons, with no font/CDN dependency."""
PATHS = {
    "bars": '<path d="M4 20V10h3v10M11 20V4h3v16M18 20v-7h3v7"/>',
    "monitor": '<circle cx="12" cy="12" r="9"/><path d="M12 3v9l7 5M12 12H3"/>',
    "person": '<circle cx="12" cy="7" r="4"/><path d="M4 21v-3a8 8 0 0 1 16 0v3z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 3"/>',
    "search": '<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',
    "database": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
    "book": '<path d="M12 5v16M12 5C8 2 4 3 2 4v15c4-2 7-1 10 2 3-3 6-4 10-2V4c-4-2-7-1-10 1z"/>',
    "chevron": '<path d="m9 5 7 7-7 7"/>',
    "document": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h4M9 12h6M9 16h6"/>',
    "bell": '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
    "chart": '<path d="m3 17 6-6 4 4 8-11M14 4h7v7"/>',
    "shield": '<path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6zM12 7v6M12 16v1"/>',
    "check": '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="m7 12 3 3 7-8"/>',
    "building": '<path d="M5 21V3h12v18M2 21h20M9 7h1M13 7h1M9 11h1M13 11h1M9 15h1M13 15h1M10 21v-3h3v3"/>',
}


def icon(name):
    return '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + PATHS[name] + '</svg>'
