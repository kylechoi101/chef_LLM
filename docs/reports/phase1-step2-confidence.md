# Phase 1 step 2 — positive-confidence tiers

231637 recipes | 229371 distinct ingredient sets | 1724 copy groups with >1 recipe | 140594 remake-language reviews | 179 contest entries

Tier 3 = loud yes (pooled ratings >= 20, or >= 3 remake reviews, or >= 10 ratings and >= 3 years active). Tier 2 = ordinary (>= 3 ratings, or a remake review, or >= 2 distinct authors). Tier 1 = whisper. Tier 0 = structural/safety exclusion.

```
               n  median_rating_n  mean_remake  contest_share  share
pos_tier                                                            
0              1              2.0        0.000          0.000  0.000
1         118471              1.0        0.000          0.001  0.511
2          90821              3.0        0.637          0.001  0.392
3          22344             15.0        3.704          0.001  0.096
```

## Largest copy groups (distinct authors)
```
                                                          n  authors                                             title
copy_group                                                                                                            
butter|eggs|flour|milk|salt                              18       16                  all purpose dinner crepes batter
baking powder|butter|egg|flour|milk|salt|sugar           16       16                      make it your way  shortcakes
baking powder|flour|milk|salt|shortening                 11       11                                basic tea biscuits
butter|eggs|flour|milk|salt|sugar                        10       10                            baked finnish pancakes
eggs|water                                               10       10  chinese confinement egg omelette with sesame oil
baking powder|butter|eggs|flour|milk|salt|sugar|vanilla   9        9                       fannie farmer sugar cookies
butter|flour|sugar                                        9        9                                      butter crust
lemons|sugar|water                                        9        9                                    basic lemonade
```

## Sample tier 3

crock pot chicken with black beans   cream cheese; creamy cajun chicken pasta; to die for crock pot roast; best ever banana cake with cream cheese frosting; yes  virginia there is a great meatloaf; jo mama s world famous spaghetti; creamy burrito casserole; best banana bread

## Sample tier 1 with most ratings (whispers that almost made it)

alouette  potatoes; bananas 4 ice cream  pie; boat house  collard greens; cream  of spinach soup  vegan; forgotten  minestrone

## Reading

- **Remake language is the strongest signal we have.** 140,594 reviews (13% of
  all 1.07M) contain explicit re-cook language ("made this again", "a keeper",
  "in our rotation"). Tier 3 recipes average 3.7 such reviews; tier 2 average
  0.6; tier 1 average 0. This is the "worth saving" signal in its digital form.
- **Half the corpus is a whisper.** Tier 1 (51%) has a median of one rating and
  no re-cook evidence. These stay positives with low weight; they are not
  negatives. Nothing here says they are bad, only that nobody has vouched.
- **Copies are rarer than expected under an exact ingredient-set key.** Only
  1,724 groups with more than one recipe; the largest is an 18-author crepe
  batter. Pooling therefore changed few tiers on Food.com. The key also
  conflates generic sets ("eggs|water") that are not one dish. Family-level
  pooling waits on the step-graph comparison from the plan amendment.
- **Contest entries are negligible** (179), so the discount is a no-op here
  but stays for sources where it matters.
- Run: default DSMLP CPU pod (no `-W`), 4 cores, 10 GB, 52 s.
  `python3 -m etl.confidence data/corpus/foodcom.parquet`.
