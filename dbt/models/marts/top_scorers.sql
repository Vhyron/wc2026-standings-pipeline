-- Per-tournament scorer leaderboard. Own goals credit no scorer.
-- Only meaningful for years with goal-event coverage (1930-1950, 2014-2026).

select
    year,
    scorer as player,
    team,
    count(*) as goals,
    row_number() over (
        partition by year
        order by count(*) desc, scorer
    ) as scorer_rank
from {{ ref('stg_goals') }}
where not is_owngoal
group by year, scorer, team
