-- Insurer market-share weights used by the generator must add up to 1.
SELECT ROUND(SUM(market_share_weight), 4) AS total_weight
FROM ref_payer
WHERE payer_type = 'Insurer'
HAVING ABS(SUM(market_share_weight) - 1) > 0.0001;
