# Feature media

The landing page's feature showcase (`components/landing/feature-showcase.tsx`) has one
media panel per feature, configured in `lib/landing-features.ts`. A feature whose `media` is
`{ kind: "placeholder" }` shows a designed tile; replace it with a picture or a video:

```ts
media: { kind: "image", src: "/landing/features/ask.webp", altKey: "marketing.features.ask.alt" }
media: { kind: "video", src: "/landing/features/ask.mp4", webm: "/landing/features/ask.webm",
         poster: "/landing/features/ask-poster.webp", altKey: "marketing.features.ask.alt" }
```

Add the `alt` text in both `lib/i18n/dictionaries.en.ts` and `dictionaries.es.ts`
(`marketing.features.<id>.alt`): describe what the picture shows, in a sentence.

## What to ship

| | Image | Video |
|---|---|---|
| Format | `.webp` | `.mp4` (H.264, for Safari) and, if you can, `.webm` |
| Shape | 4:3, at least 1200 px wide | 4:3, 1200 px wide |
| Size | under 150 KB | under 3 MB, under 12 s, no sound |
| Also needed | | a `poster` image: shown before it loads, and always under reduced motion |

A video plays only while its feature is the one in view, is muted and loops, and is paused
for anyone who asked their system for reduced motion. Do not rely on it to say something the
text does not: some visitors will only ever see the poster.

## Rights

Only use images and video you made or are allowed to use. Record the source and licence next
to the file (a line in this README is enough). Never use real patient studies, and not the
RSNA/Kaggle samples under `real_data/`, whose licence forbids redistributing them.

## Files here

None yet: the "See" feature uses `/landing/analysis/xray.webp`, the same file as the demo.
