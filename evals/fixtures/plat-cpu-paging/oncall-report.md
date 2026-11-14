# On-call report, October

- 212 pages. 171 were HighCPU or HighMemory during the nightly batch import,
  with no customer impact. 38 were Any5xx firing on single errors.
- The two real incidents (a bad config push, a payment-provider outage) were
  reported by customers before anyone was paged on them: error rate sat at
  2-4% for 40 minutes, which looked like normal Any5xx noise.
- Product target for checkout: 99.9% of requests succeed and 99% complete in
  under 800 ms, measured over 30 days.
