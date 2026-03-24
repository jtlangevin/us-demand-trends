<div style="text-align: center; font-size: 1.2em; margin-top: 10px;">
  ⚡ Key demand-side snapshots and trends for the US energy sector ⚡
</div>

<br>

### 🤝 Contributions
* Spot a problem with the results or have a request for an improvement? [Submit an issue](https://github.com/jtlangevin/us-demand-trends/issues).
* Help develop the underlying code via [GitHub](https://github.com/jtlangevin/us-demand-trends).

<br>

<details style="background-color: #f8f9fa; border: 1px solid #e1e4e8; border-radius: 8px; padding: 20px; margin-bottom: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
  <summary style="cursor: pointer; font-weight: bold; font-size: 1.1em; outline: none;">📖 Table of Contents (Click to expand)</summary>
  
  <ul class="dynamic-toc">
    <li data-category="Affordability">Affordability <ul id="list-affordability"></ul></li>
    <li data-category="Technology Choice">Technology Choice <ul id="list-tech"></ul></li>
    <li data-category="Electric Load Growth">Electric Load Growth <ul id="list-load"></ul></li>
    <li data-category="Grid Edge">Grid Edge <ul id="list-grid"></ul></li>
    <li data-category="Economic Growth">Economic Growth and Competitiveness <ul id="list-econ"></ul></li>
  </ul>
</details>

<style>
  .dynamic-toc { list-style: none; padding-left: 0; margin-top: 15px; }
  .dynamic-toc > li { font-weight: bold; margin-top: 15px; }
  
  /* Category Emojis */
  li[data-category="Affordability"]::before { content: "💸 "; }
  li[data-category="Technology Choice"]::before { content: "⚙️ "; }
  li[data-category="Electric Load Growth"]::before { content: "📈 "; }
  li[data-category="Grid Edge"]::before { content: "🌐 "; }
  li[data-category="Economic Growth"]::before { content: "🏗️ "; }

  /* Sub-bullets styling */
  .dynamic-toc ul { font-weight: normal; list-style-type: circle; padding-left: 25px; margin-top: 5px; }
  
  /* Optional: Smooth out the summary arrow */
  details summary::-webkit-details-marker { display: none; }
  details summary { list-style: none; }
  details summary::before { content: "▶ "; font-size: 0.8em; margin-right: 5px; display: inline-block; transition: transform 0.2s; }
  details[open] summary::before { transform: rotate(90deg); }
</style>



<hr style="border: 2px solid #333; margin: 30px 0;">

# Affordability

### Housing Construction
This dashboard visualizes the speed and cost of new housing development at the county level, illustrating the regions where new housing is growing the fastest and/or housing construction costs are the lowest, while also indicating the typical time it takes to construct single and multi family housing.

<iframe src="graphics/permits_construction_costs.html" width="100%" height="1450px" frameborder="0" scrolling="no"></iframe>

---

### Homeowners Insurance Premiums
Property insurance is a key component of overall homeownership costs. This dashboard maps the median annual cost of homeowners insurance at the county level across the U.S. for all homeowners, providing a highly localized view of where insurance rates are compounding regional housing affordability challenges.

<div align="center">
  <iframe src="graphics/insurance_costs.html" width="85%" height="750px" frameborder="0" scrolling="no"></iframe>
</div>

---

### Household Energy Burden
Energy burden—the percentage of household income spent on energy bills—is a critical affordability metric. These plots show both the *total* energy burden (across fuels) and the *electric-only* energy burden, illustrating where communities are most vulnerable to price shocks and where electric bills dominate household expenses.

<iframe src="graphics/energy_burden_maps_bar.html" width="100%" height="1250px" frameborder="0" scrolling="no"></iframe>

<hr style="border: 2px solid #333; margin: 30px 0;">

# Technology Choice

### Heating Equipment Penetration
Space heating is one of the largest drivers of residential energy consumption. This visualization maps the current baseline of homes utilizing electric heat and tracks the net shift in that percentage between 2020 and 2024, highlighting regional trends in heating equipment choices.

<iframe src="graphics/heating_equip_map.html" width="100%" height="750px" frameborder="0" scrolling="no"></iframe>

---

### Fuel Price Comparisons
The spread between electricity and natural gas prices heavily influences electrification economics. This state-by-state analysis highlights where the pricing structure favors natural gas (lower ratio) versus where electricity is more cost-competitive, broken down by residential and commercial sectors.

<iframe src="graphics/fuel_price_ratio_maps_bar.html" width="100%" height="1250px" frameborder="0" scrolling="no"></iframe>

---

### Price Trends by Fuel

Recent changes in energy prices and perceived fuel price volatility can influence consumer decision-making about what types of equipment to adopt. The plots below compare post-2000 trends in inflation-adjusted fuel prices with trends in inflation-adjusted consumer fuel expenditures over the same period, breaking out trends by electricity and natural gas and by residential and commercial consumer types.

<iframe src="graphics/price_expend_trend.html" width="100%" height="650px" frameborder="0" scrolling="no"></iframe>

<hr style="border: 2px solid #333; margin: 30px 0;">


# Electric Load Growth

### Annual Demand (Recent Growth)
Electric load growth is accelerating after years of stagnation. This dashboard details the 5-year and 2-year growth trajectories for total load across the U.S., decomposing the growth into its constituent sectors (Residential, Commercial, Industrial) to reveal the underlying structural drivers.

<iframe src="graphics/annual_sales.html" width="100%" height="1150px" frameborder="0" scrolling="no"></iframe>

---

### Peak Demand (Recent Growth)
If the underlying drivers of load growth change the timing of electricity consumption, the seasonality of peak demand on the grid could shift as well. This dashboard explores the current ratio of summer vs. winter peaks in demand across the country, while identifying the states experiencing the fastest growth in winter and summer peak demand.

<iframe src="graphics/peak_demand.html" width="100%" height="1050px" frameborder="0" scrolling="no"></iframe>

---

### Peak Demand (Forecasted Growth)
This dashboard visualizes forecasted 5- and 10-year growth in peak demand for US utilities and ISOs/RTOs. It explicitly separates retail utilities (circles) from wholesale Regional Transmission Organizations (diamonds) to provide a comprehensive view of emerging load hotspots.

<iframe src="graphics/load_forecasts.html" width="100%" height="750px" frameborder="0" scrolling="no"></iframe>


<hr style="border: 2px solid #333; margin: 30px 0;">

# Grid Edge

### Demand-side Management Deployment
Energy efficiency and demand response are critical demand-side resources for maintaining grid reliability in the face of load growth. Here we map the scale of these demand-side resources and show their 5-year growth by sector, illustrating where utilities are successfully offsetting load growth via demand-side interventions.

<iframe src="graphics/dsm_potential.html" width="100%" height="900px" frameborder="0" scrolling="no"></iframe>

---

### Utility Expenditures
To serve growing electricity demand and manage new technology operation at the grid edge, the physical grid must be maintained and expanded. This chart shows utility spending on operation and maintenance of generation, transmission, and distribution infrastructure, highlighting the states with the largest expenditures and the 10-year trend in these expenditures for California.

<iframe src="graphics/utility_costs.html" width="100%" height="1050px" frameborder="0" scrolling="no"></iframe>

<hr style="border: 2px solid #333; margin: 30px 0;">

# Economic Growth and Competitiveness

### Buildings Jobs
Buildings-related jobs – jobs to design, construct, operate, and retrofit buildings – are an important component of overall US employment numbers. This chart shows the trend in buildings-related jobs over the past two decades.

<div align="center">
  <iframe src="graphics/building_jobs_trend.html" width="100%" height="700px" frameborder="0" scrolling="no"></iframe>
</div>

<hr style="border: 2px solid #333; margin: 30px 0;">


### Exports of Buildings-related Products

Buildings sector and other demand-side products are important players in US export markets. These charts demonstrate the magnitude of export markets for such products, the historical trends for those markets, and which countries the US is exporting the products to.

<div align="center">
  <iframe src="graphics/exports.html" width="100%" height="1350px" frameborder="0" scrolling="no"></iframe>
</div>

<hr style="border: 2px solid #333; margin: 30px 0;">

### GDP from Buildings Activities
Activities in commercial and residential buildings contribute substantially to U.S. gross domestic product (GDP). This chart shows the wedge of those contributions together with industrial/non-building activities over the past two decades.

<div align="center">
  <iframe src="graphics/gdp_contributions.html" width="100%" height="750px" frameborder="0" scrolling="no"></iframe>
</div>
<hr style="border: 2px solid #333; margin: 30px 0;">


<script>
document.addEventListener("DOMContentLoaded", function() {
  const sections = {
    "Affordability": "list-affordability",
    "Technology Choice": "list-tech",
    "Electric Load Growth": "list-load",
    "Grid Edge": "list-grid",
    "Economic Growth and Competitiveness": "list-econ"
  };

  // Find all H1 and H2 sections (the main categories)
  document.querySelectorAll('h1, h2').forEach(categoryHeader => {
    // Clean the header text by removing link icons and extra spaces
    const catName = categoryHeader.innerText.replace('🔗', '').trim();
    const targetListId = sections[catName];
    
    if (targetListId) {
      const targetUl = document.getElementById(targetListId);
      let nextEl = categoryHeader.nextElementSibling;
      
      // Look for all H3 headers until we hit the next major section (H1 or H2)
      while (nextEl && nextEl.tagName !== 'H1' && nextEl.tagName !== 'H2') {
        
        // Only grab H3 tags for the sub-bullets
        if (nextEl.tagName === 'H3') {
          // GitHub Pages Markdown generates IDs for all headers automatically
          const link = nextEl.querySelector('a') ? nextEl.querySelector('a').getAttribute('href') : '#' + nextEl.id;
          const title = nextEl.innerText.replace('🔗', '').trim();
          
          const li = document.createElement('li');
          li.innerHTML = `<a href="${link}">${title}</a>`;
          targetUl.appendChild(li);
        }
        
        // Move to the next element down the page
        nextEl = nextEl.nextElementSibling;
      }
      
      // Optional: If a category has no H3 sub-bullets, hide the empty circle bullet
      if (targetUl.children.length === 0) {
          targetUl.style.display = 'none';
      }
    }
  });
});
</script>
