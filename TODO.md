# Implementation TODO

## Steps

- [x] 1. Create TODO.md to track progress
- [x] 2. **crawler.py**: Add resource blocking (images, CSS, fonts, media)
- [x] 3. **crawler.py**: Remove `networkidle` wait
- [x] 4. **crawler.py**: Add Render-friendly Chromium launch flags
- [x] 5. **crawler.py**: Add explicit `page.close()` and `context.close()`
- [x] 6. **app.py**: Reduce `max_pages` from 500 to 10
- [x] 7. **config.json**: Update default `max_pages` from 200 to 10
- [x] 8. **render.yaml**: Increase Gunicorn timeout from 120 to 300

