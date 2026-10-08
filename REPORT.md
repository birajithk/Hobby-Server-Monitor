# Final Report — Hobby Server Monitor

> Delete this instruction block and fill in the sections below. Be specific
> and honest. See the "Final Report" and "Decisions we are leaving to you" sections
> of [README.md](README.md) for what's expected here.

## Time Spent

Rough breakdown, not a timesheet.

| Area | Time |
| --- | --- |
| Backend (API, auth, authorization) | |
| Dashboard (Astro frontend) | |
| LXD integration | |
| Background collector / TSDB | |
| Debugging | |
| Documentation / report | |
| **Total** | |

## Key Decisions

Pick at **more than three** of the open questions from README.md's "Decisions we are
leaving to you" and answer them properly: what you chose, the alternatives
you considered, and why you rejected them.

## Issues Encountered and Solutions

The real ones — including what you tried first and got wrong.

## What You Learned

## Bonus Features Implemented

## Resource Measurements

### 1. Benchmark Objective

The task requires the monitoring application to consume
minimal CPU and RAM because it runs on the same machine
it monitors.

Resource measurements were performed on the deployed
application rather than the development servers.

The benchmark covers:

- Falcon API running under Gunicorn.
- Independent TinyFlux metrics collector.
- Nginx serving the compiled Astro frontend.
- Browser usage with zero, one and three dashboard tabs.
- Short-term SQLite and TinyFlux storage growth.

### 2. Test Environment

Verification date: 2026-10-08

| Component | Specification |
| --- | --- |
| Operating system | Ubuntu 24.04.4 LTS |
| Architecture | x86_64 |
| Processor | Intel Core i9-11900H @ 2.50 GHz |
| Physical CPU cores | 8 |
| Logical CPU threads | 16 |
| Host RAM | 15,763.51 MiB |
| LXD version | 5.21.8 LTS |
| Containers present | 3 |
| Running containers | 1 |
| Stopped containers | 2 |
| Falcon server | Gunicorn, 1 worker |
| Metrics polling interval | 10 seconds |
| Frontend deployment | Static Astro through Nginx |

The operating system was running normal desktop
workloads during testing.

The measurements represent this development machine
and should not be interpreted as the minimum hardware
requirements for every deployment.

### 3. Measurement Methodology

The benchmarking script is located at:

deploy/scripts/measure-resources.py

The script reads resource counters from systemd
using the following properties:

- ActiveState
- MainPID
- MemoryCurrent
- CPUUsageNSec

It collects service memory measurements approximately
every five seconds.

Average CPU utilization is calculated from the
difference in CPUUsageNSec between the beginning
and end of each test.

CPU percentages are normalized so that 100%
corresponds to one fully utilized logical CPU.

Average RAM is calculated from sampled
MemoryCurrent values.

These are systemd control-group memory measurements
and may include memory accounted to the service
beyond its process-resident pages.

Three measurement scenarios were executed
sequentially, each lasting approximately 60 seconds.

Commands:

sudo python3 deploy/scripts/measure-resources.py no-tabs 60

sudo python3 deploy/scripts/measure-resources.py one-tab 60

sudo python3 deploy/scripts/measure-resources.py three-tabs 60

### 4. No Browser Tabs

Duration: 60.03 seconds

| Service | Average CPU | Average RAM | Peak sampled RAM |
| --- | ---: | ---: | ---: |
| Falcon API | 0.015% | 42.55 MiB | 42.74 MiB |
| Metrics collector | 0.303% | 38.36 MiB | 38.50 MiB |
| Nginx | 0.000% | 18.39 MiB | 18.39 MiB |

Sum of average service memory: 99.30 MiB

Sum of average service CPU usage: 0.318%

SQLite net size change: 0 bytes

TinyFlux net size change: +7,199 bytes

The collector continued running with no browser
tabs open. Metrics collection therefore did not
depend on an active dashboard session.

### 5. One Dashboard Tab

Duration: 60.01 seconds

| Service | Average CPU | Average RAM | Peak sampled RAM |
| --- | ---: | ---: | ---: |
| Falcon API | 0.101% | 42.95 MiB | 43.39 MiB |
| Metrics collector | 0.429% | 38.53 MiB | 38.62 MiB |
| Nginx | 0.022% | 18.76 MiB | 19.47 MiB |

Sum of average service memory: 100.24 MiB

Sum of average service CPU usage: 0.552%

SQLite net size change: 0 bytes

TinyFlux net size change: +8,439 bytes

### 6. Three Dashboard Tabs

Duration: 60.03 seconds

| Service | Average CPU | Average RAM | Peak sampled RAM |
| --- | ---: | ---: | ---: |
| Falcon API | 0.146% | 44.40 MiB | 45.27 MiB |
| Metrics collector | 0.331% | 38.69 MiB | 39.04 MiB |
| Nginx | 0.019% | 19.09 MiB | 19.91 MiB |

Sum of average service memory: 102.18 MiB

Sum of average service CPU usage: 0.496%

SQLite net size change: 0 bytes

TinyFlux net size change: +7,196 bytes

The collector remained a single independent
systemd service.

The dashboard uses visibility-aware polling,
which may reduce the activity of background tabs.

The test does not establish how the application
would behave with three independently active
clients on different machines.

### 7. Comparison

| Metric | No tabs | 1 tab | 3 tabs |
| --- | ---: | ---: | ---: |
| Combined average RAM (MiB) | 99.30 | 100.24 | 102.18 |
| Combined CPU (%) | 0.318 | 0.552 | 0.496 |
| TinyFlux growth (bytes) | 7,199 | 8,439 | 7,196 |

The difference between the no-tab and three-tab
measurements was 2.88 MiB of combined average
service memory.

The CPU measurements were low in all three tests.

However, the tests were short and sequential.
Normal host activity, garbage collection, file
caching and background processes can affect
individual readings.

No statistical confidence interval or repeated
trial analysis was performed.

### 8. Storage Growth

The observed TinyFlux file size changes were:

- No tabs: +7,199 bytes in approximately 60 seconds.
- One tab: +8,439 bytes in approximately 60 seconds.
- Three tabs: +7,196 bytes in approximately 60 seconds.

The collector monitored three LXD containers,
including stopped containers.

SQLite did not change in size during these
measurement windows.

The observed TinyFlux growth ranged from
approximately 7.2 KB to 8.4 KB per minute.

If this short-term growth continued without
retention or compaction, the corresponding
linear estimate would be roughly 10 to 12 MB
per day for the tested workload.

This is an illustrative extrapolation,
not a measured daily or monthly storage footprint.

The implementation also includes:

- A configurable raw-metric retention period.
- Periodic five-minute metric aggregation.
- Retention cleanup of older measurements.

Actual long-duration bounded-storage behavior
requires a separate verification test.

### 9. Resource Efficiency Assessment

The measured deployment used approximately
99 to 102 MiB of combined average service memory
across the three tested scenarios.

The independent collector averaged approximately
38 to 39 MiB of control-group memory.

The Falcon API averaged approximately
43 to 44 MiB.

The measured CPU footprint was low during
these short tests.

The static Astro frontend does not require
a continuously running production Node.js server.

The independent collector polls LXD once per
configured interval rather than creating
a separate collection process per browser tab.

These measurements support the decision to
use Falcon, Astro, systemd and an independent
TinyFlux collector for this single-host tool.

### 10. Measurement Limitations

The following were not established by these tests:

- Behavior on a much smaller host.
- Maximum supported number of containers.
- Sustained concurrent-user performance.
- Long-term memory stability.
- Actual 24-hour and 30-day storage size.
- CPU and RAM behavior during an LXD outage.
- Browser-side CPU and RAM consumption.
- Performance under heavy terminal execution
  or simultaneous container management actions.

These remain known measurement limitations
unless further tests are performed.

## Known Limitations

What is unfinished, broken, simulated, or deliberately cut — and why.

## AI Tool Usage

Which tools, for which parts of the system, what you accepted as-is, and
what you rejected or had to fix. You should be able to explain every line
you submit, AI-assisted or not.
