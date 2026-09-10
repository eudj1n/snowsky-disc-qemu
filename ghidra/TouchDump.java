import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.app.decompiler.*;
import java.util.*;
public class TouchDump extends GhidraScript {
  public void run() throws Exception {
    String[] needles = {"/dev/input/event%d","cst816t","SCREEN_ROT","tp_","touch"};
    DecompInterface di = new DecompInterface(); di.openProgram(currentProgram);
    Set<Function> targets = new LinkedHashSet<>();
    DataIterator dit = currentProgram.getListing().getDefinedData(true);
    for (Data d : (Iterable<Data>)()->dit) {
      String s=null; try{Object v=d.getValue(); if(v!=null)s=v.toString();}catch(Exception e){}
      if(s==null) continue;
      boolean hit=false; for(String n:needles) if(s.contains(n)){hit=true;break;}
      if(!hit) continue;
      println("STR @"+d.getAddress()+" = "+s.replace("\n","\\n"));
      ReferenceIterator ri=currentProgram.getReferenceManager().getReferencesTo(d.getAddress());
      int c=0;
      for(Reference r:(Iterable<Reference>)()->ri){ c++;
        Function f=getFunctionContaining(r.getFromAddress());
        if(f!=null){ targets.add(f); println("   xref from "+f.getName()+" @"+r.getFromAddress()); }
      }
      if(c==0) println("   (no xrefs)");
    }
    println("=== decompiling "+targets.size()+" funcs ===");
    for(Function f: targets){
      println("//////// FUNC "+f.getName()+" @"+f.getEntryPoint()+" ////////");
      DecompileResults dr=di.decompileFunction(f,90,monitor);
      if(dr!=null&&dr.getDecompiledFunction()!=null) println(dr.getDecompiledFunction().getC());
    }
  }
}
