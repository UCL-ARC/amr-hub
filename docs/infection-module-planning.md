# Planning the Inclusion of Infection Dynamics in AMR-Hub

## Overview

In order to begin tracking the infection dynamics of the organisms and strains that have been identified to be of interest, AMR-Hub is in need of a proper infection module that keeps track of all organisms and their properties, tests for pathogen identification, facilitates the spread of infections, and updates disease progression every step. Below is a brief foray into the way infections are typically represented within medical and research contexts, and how the AMR-Hub infection module can progress in light of this.

## Stages of Infection [1, 2]

1. **Exposure (Via Chain of Infection)**
   - Susceptible host comes into contact with causative agent (pathogen) in a reservoir (environment that can sustain the pathogen).
     - Susceptibility of host can depend on immune response/deficiency (affected by antibodies, age, etc.) and strain of pathogen.
     - Most common reservoirs: humans, animals, water, food, environmental surfaces.
   - Causative agent leaves its reservoir through a portal of exit (e.g. bodily fluids) and enters the host through a portal of entry (e.g. respiratory tract, intestines, wounds).
     - Transmission occurs if a pathogen can survive the entry/exit, which is why contact (direct or indirect) is the most common mode of transmission.
2. **Incubation Stage**
   - Pathogen has successfully entered host and begins to multiply. Host remains asymptomatic.
3. **Prodromal Stage**
   - Initial appearance of mild or vague symptoms due to immune system activation (e.g. inflammation, fever, pain).
4. **Illness Stage**
   - Disease-specific symptoms appear. Peak of infection; high likelihood of contagion.
   - Successfully combating the pathogen will cause it to enter a period of decline.
5. **Convalescence Stage**
   - Period of recovery and healing. Symptoms fade and host system attempts to return to baseline.

## References

[1] Bowen, C. (2024). Clinical Nursing Skills, 6.1: Infection cycle. LibreTexts. <https://med.libretexts.org/Bookshelves/Nursing/Clinical_Nursing_Skills_(OpenStax)/06%3A_Infection_Prevention_Techniques_and_Safety_in_the_Clinical_Setting/6.01%3A_Infection_Cycle>.

[2] Ernstmeyer, K., & Christman, E. (Eds.). (2024). Nursing Fundamentals 2e, 9.4 Infection. Open RN | WisTech Open. <https://wtcs.pressbooks.pub/nursingfundamentals/chapter/9-4-infection/>.
