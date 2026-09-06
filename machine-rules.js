// Generated catalog from machine-rules.json; matching logic mirrors machine_rules.py.
const machineRules={
  "version": 1,
  "machine_pattern": "\\b(graphtec|roland|camm[- ]?1|cricut|silhouette|cameo|plotter|vinyl cutter|cutting machine|cutting plotter|uscutter|summa|gcc expert|seiki)\\b",
  "accessory_pattern": "^(replacement|blade|blades|pen holder|carrying case|dust cover|power (cord|adapter)|cutting mat|adapter|vinyl roll)\\b|\\b(for (silhouette|cameo|cricut)|parts only|not working|broken|no cutters|no blade)\\b",
  "models": [
    {
      "id": "cameo-3",
      "pattern": "\\bcameo\\s*3\\b",
      "name": "Silhouette Cameo 3",
      "tools": "Blade in left holder and compatible pen in right holder; no tool swap between draw and cut steps. Confirm both tools are included.",
      "working_width": "12 in nominal working width; drawing margins depend on setup",
      "body_width": "Unverified — request seller measurement",
      "roll": "500 ft paper spool NOT verified. The built-in crosscutter is manual; unattended sheet separation needs a separate solution.",
      "sources": ["https://www.silhcdn.com/m/d/user-guides/cameo-3-en.pdf", "https://www.silhouetteamerica.com/pen-holder"]
    },
    {
      "id": "cameo-5",
      "pattern": "\\bcameo\\s*5\\b(?!\\s*(plus|alpha|α|\\+))",
      "name": "Silhouette Cameo 5 (standard)",
      "tools": "Blade in Tool Holder 1 plus the compatible Tool Holder 2 pen holder (Type C). Confirm that specific pen holder is included; a Tool 1 pen holder would require a swap.",
      "working_width": "12 in nominal working width; drawing margins depend on setup",
      "body_width": "22.28 in (standard model)",
      "roll": "500 ft plain-paper feeding and automatic sheet separation NOT verified. Dual tools alone do not make an unattended roll-fed system.",
      "sources": ["https://www.silhouetteeurope.eu/media/catalog/product/attachment/c/a/cameo5-um-151_protect_6.pdf", "https://www.silhouetteamerica.com/catalog/product/view/id/2437/"]
    },
    {
      "id": "cricut-explore-air-2",
      "pattern": "\\bcricut\\s+explore\\s+air\\s*2\\b",
      "name": "Cricut Explore Air 2",
      "tools": "Pen in Clamp A and blade in Clamp B; confirm both are included.",
      "working_width": "Unverified — confirm drawing area for chosen material",
      "body_width": "Unverified — request seller measurement",
      "roll": "Not verified for your unattended 500 ft paper spool. Treat as a dual-tool development candidate, not a complete roll-fed robot.",
      "sources": ["https://help.cricut.com/hc/en-us/articles/1500005393621-Cricut-Explore-3-Quick-Start-Guide", "https://help.cricut.com/hc/en-us/articles/26322630938647-How-to-change-the-machine-blade-and-pens-Cricut-Explore-series-Cricut-Maker-series-and-Cricut-Venture-machines"]
    }
  ]
};
function machineFit(row){
 const title=row.title||'';
 const isMachine=new RegExp(machineRules.machine_pattern,'i').test(title+' '+(row.matched_query||''))||(row.watch_ids||[]).includes('primary-plotter');
 if(!isMachine)return {is_machine:false,eligible:true};
 if(new RegExp(machineRules.accessory_pattern,'i').test(title))return {is_machine:true,eligible:false};
 const models=machineRules.models.filter(m=>new RegExp(m.pattern,'i').test(title));
 if(models.length!==1||/\bcameo\s*[124]\b/i.test(title))return {is_machine:true,eligible:false};
 return {is_machine:true,eligible:true,model:models[0]};
}
function filterMachines(board){
 const records=new Map([...(board.hidden_machines||[]),...board.listings].map(x=>[x.id,x]));
 board.listings=[];board.hidden_machines=[];
 for(const row of records.values()){row.machine_fit=machineFit(row);(row.machine_fit.eligible?board.listings:board.hidden_machines).push(row);}
}
