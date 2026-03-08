# TTC subway delays, January 2014 – August 2026: what to act on first

*For: operations and performance managers. Source: Toronto Open Data, "TTC Subway Delay Data" (every yearly
file, downloaded through the CKAN API). Every number below comes from the pipeline in this repository
(`reports/kpi_summary.md`, `reports/data_quality.md`). The data ends on 31 August 2026, so "2026" means
January–August, compared with January–August 2025.*

## The short version

1. **A few causes make up most of the lost time.** 41 of the 207 delay codes that cost any time account for
   80% of the 682,828 minutes of delay logged since 2014. The ten largest cause almost half (46.8%).
2. **The largest causes involve passengers, not trains.** Disorderly patrons, ill or injured customers,
   people at track level and other security incidents made up about a third (33.2%) of 2025's delay minutes.
3. **Delays got longer, then partly recovered.** Total delay minutes doubled from 35,496 in 2015 to 73,094
   in 2022. They have stayed near that level since (70,755 in 2025), but minutes per incident fell from
   3.68 (2022) to 2.76 (2025).
4. **Line 2 is getting worse.** In the 12 months to August 2026, Line 2 lost 33,138 minutes, 18% more than in
   the 12 months before. Line 1 lost 37,197, 12% fewer.
5. **Counting incidents points at the wrong stations.** The five stations that log the most incidents
   (Bloor-Yonge, Kennedy, Finch, Kipling, TMU) are among the stations whose incidents cost the *fewest*
   minutes. Ranked fairly, the stations to look at first are on the northern part of Line 1.

## 1. Which causes to act on (Pareto)

All years, whole network:

| Rank | Code | Cause | Share of minutes | Cumulative |
|---:|---|---|---:|---:|
| 1 | SUDP | Disorderly patron | 9.4% | 9.4% |
| 2 | MUI | Injured/ill customer on train, transported | 5.7% | 15.1% |
| 3 | SUUT | Unauthorized person at track level | 5.6% | 20.7% |
| 4 | MUIR | Injured/ill customer on train, refused medical aid | 5.1% | 25.8% |
| 5 | MUPR1 | Priority One, train in contact with a person | 4.5% | 30.3% |
| 6 | SUO | Security, other | 4.4% | 34.7% |
| 7 | MUPLB | Fire/smoke at track level, TTC source | 3.8% | 38.4% |
| 8 | MUPAA | Passenger alarm, no trouble found | 3.2% | 41.6% |
| 9 | PUOPO | Train door monitoring (one-person train operation) | 2.8% | 44.5% |
| 10 | MUATC | Automatic train control project | 2.3% | 46.8% |

In 2025, the last full year, 29 of the 118 codes that cost any time made up 80% of delay minutes. The top five
were disorderly patrons (10.8%), customers refusing medical aid (6.8%), people at track level (5.5%), customers
taken to hospital (5.3%) and other security incidents (4.8%).

**What changed in the mix:**

- **Security and passenger behaviour** (codes starting with S) grew from 14.9% of minutes in 2014 to a peak
  of 38.8% in 2023. It fell back to 26.9% in 2025 and was 24.9% in 2026. Disorderly patrons alone peaked
  at 13.5% in 2023.
- **Plant: track, signals, power and stations** (codes starting with P) grew to 22.8% of minutes in 2025
  and 23.2% in 2026. Door monitoring for one-person train operation (PUOPO) barely existed before 2020
  (74 minutes in 2019). It reached 5,070 minutes (6.8%) in 2024 and 3,398 in 2025, and it is Line 1's
  second-largest cause (7.9% in 2025).
- **Weather is now a top-ten cause.** Weather reports (MUWEA) went from 45 minutes in 2023 to 2,745 in 2025.
  Ice and snow (PUTIS) went from 239 minutes in 2025 to 3,888 in 2026, all of it in one storm
  (24–31 January). January 2026 lost 12,372 minutes, 94% more than January 2025.
- **Priority One incidents** (a train in contact with a person) fell from 5.4% of minutes in 2022 to 2.4% in 2025.
- **Line 4 Sheppard is different.** Its largest 2025 cause was track switch failures (PUSSW, 11.3%), followed
  by operators violating signals (7.5%).

## 2. What changed over time

| Year | Incidents | Delay minutes | Minutes per incident | Minutes vs. previous year |
|---|---:|---:|---:|---:|
| 2015 | 21,467 | 35,496 | 1.65 | −13.8% |
| 2019 | 19,143 | 45,493 | 2.38 | −5.7% |
| 2020 | 14,759 | 46,518 | 3.15 | +2.3% |
| 2022 | 19,881 | 73,094 | 3.68 | +36.7% |
| 2023 | 22,943 | 68,146 | 2.97 | −6.8% |
| 2024 | 26,450 | 74,266 | 2.81 | +9.0% |
| 2025 | 25,680 | 70,755 | 2.76 | −4.7% |
| 2026 (Jan–Aug) | 19,729 | 51,293 | 2.60 | +5.2% (vs. Jan–Aug 2025) |

- In 2020–2022, fewer incidents were logged but each one cost more time. In 2020, 46.5% of incidents
  delayed a train, against 23.6% in 2015. Since 2023, more incidents are logged (26,450 in 2024) and each
  costs less.
- In 2026 to date, incidents are up 13.5% on the same months of 2025. Minutes are up only 5.2%, and most of
  that came from the January storm.
- Rolling 12 months to August 2026: 73,268 minutes across the network. The total is flat (73,434 a year
  earlier), but the lines have moved in opposite directions: Line 2 is up 18%, Line 1 is down 12% and
  Line 4 is roughly flat (2,933 vs. 2,999).

## 3. Which stations matter, ranked fairly

**The problem with simple rankings.** Ranking stations by number of incidents rewards quiet stations and
punishes busy terminals and interchanges. Ranking by average minutes per incident has the opposite flaw: a
station with 90 incidents can top the list after one long delay. This ranking uses the second measure but
**shrinks** each station's average toward its line's average. Stations with few incidents are pulled most
of the way, and stations with thousands of incidents keep their own number (empirical Bayes; see the README).

**Last 36 months (September 2023 – August 2026).** These are the stations with the most minutes lost per
incident after shrinkage. Line 1's average is 2.88 minutes.

| Rank | Station | Incidents | Raw average | After shrinkage |
|---:|---|---:|---:|---:|
| 1 | Yorkdale (Line 1) | 617 | 5.37 | 4.85 |
| 2 | Glencairn (Line 1) | 423 | 5.33 | 4.65 |
| 3 | Sheppard West (Line 1) | 1,038 | 4.70 | 4.46 |
| 4 | Museum (Line 1) | 520 | 4.87 | 4.40 |
| 5 | Rosedale (Line 1) | 768 | 4.70 | 4.38 |
| 6 | Lawrence (Line 1) | 877 | 4.66 | 4.38 |
| 7 | York Mills (Line 1) | 872 | 4.22 | 4.01 |
| 8 | Summerhill (Line 1) | 557 | 4.19 | 3.89 |

The top eight are all on Line 1, and most are on its northern sections. The highest Line 2 station is
Old Mill (rank 10). The five busiest stations by incident count rank near the bottom on minutes per incident
(of 74 stations ranked): Bloor-Yonge on Line 1 is 72nd, Kennedy on Line 2 is 62nd, Finch 67th, Kipling 52nd
and TMU 73rd. Their incidents are frequent but short.

**Which stations move, and why.**

- Over 36 months, most stations have hundreds of incidents, so shrinkage moves ranks only a little (1.4
  places on average). The largest move is Bessarion on Line 4, which rose 13 places. It had only 240
  incidents, so its low average (2.00) was pulled 38% of the way toward Line 4's higher average (3.12).
- Over the last 12 months there are fewer incidents per station (median 287), and 11 stations move 5 or more
  places. Bessarion rises 12 places, Runnymede 10 and Dufferin 9. All three have low raw averages
  supported by few incidents.
- **A caution that shrinkage does not fix.** The two worst stations of the last 12 months, Glencairn (8.81
  minutes per incident) and Woodbine (6.93), are there because of one incident each in the January 2026
  storm: 622 and 827 minutes of ice and snow delay. Without that one incident, their averages are 4.72 and
  4.41. Shrinkage corrects for small samples, not for one-off extreme events. Read the 12-month list
  next to the 36-month list.
- Across all years (2014 onward), the six Line 3 Scarborough stations rank 1st to 6th. That line averaged
  6.60 minutes per incident, against 2.4–2.9 elsewhere. It closed on 24 July 2023, so it is excluded from
  rankings for periods that start after that date.

## 4. Suggested priorities

1. **Treat passenger and security incidents as one program.** Disorderly patrons, people at track level,
   ill customers and other security incidents cost a third of all minutes, more than all equipment causes
   combined.
2. **Reduce door-monitoring delays on Line 1.** PUOPO is a new and persistent cause tied to one-person
   train operation.
3. **Plan for winter.** Weather and ice/snow codes went from almost nothing to two top-ten causes, and the
   week of 24–31 January 2026 alone lost about 7,200 minutes across all causes.
4. **Investigate Line 2's rise and the northern Line 1 stations.** Line 2's 12-month minutes rose 18%.
   Yorkdale, Glencairn, Sheppard West and Lawrence have stayed near the top of the ranking over three years.
5. **Track monthly.** The Power BI report's Trend page shows rolling 12-month minutes by line. That is the
   simplest way to see whether these actions work.

## 5. Limits of the data

- **No denominators.** The files hold no ridership, train trips or service hours, so this analysis cannot
  compare "delays per passenger" across lines or years. Minutes per incident measures how severe incidents
  are, not how often they happen.
- **Most incidents cost no time.** In 2025, 64.6% of logged incidents recorded 0 minutes of delay. Changes
  in how incidents are logged (for example, more logging since 2023) change incident counts more than
  they change minutes.
- **Codes change.** New codes appear over time (door monitoring, for example), and 27 codes in the data are
  in neither published code list (0.61% of rows). Grouping codes into categories by their first letter
  is this project's choice, not an official TTC grouping.
- **Locations are free text.** 93.2% of rows were matched to a station. The rest are line-wide entries
  (4.7%), yards and other facilities (1.2%), stretches between stations (0.8%) and unmatched text (267 rows,
  0.10%). Only matched stations are ranked.
- **Extreme values are kept.** Ten incidents of more than 600 minutes are listed in the data-quality report.
  They include a 999-minute record from 2015 that looks like a placeholder. One such incident can move a
  year's or a station's numbers.
- **Duplicates.** 269 exact duplicate rows (0.10%) were removed. Row counts reconcile with the source files
  for every year, and the 2025+ file matches the open-data portal's own record count (45,475).
- **The ranking model is simple.** It assumes station averages are roughly normally spread around their
  line's average. Delay minutes are very skewed, which is why single extreme incidents still matter.
