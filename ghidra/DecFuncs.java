import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.app.decompiler.*;
public class DecFuncs extends GhidraScript {
  public void run() throws Exception {
    String[] addrs = getScriptArgs();
    DecompInterface di=new DecompInterface(); di.openProgram(currentProgram);
    for(String a: addrs){
      Address ad=currentProgram.getAddressFactory().getAddress(a);
      Function f=getFunctionContaining(ad);
      if(f==null){ println("NO FUNC @"+a); continue; }
      println("//////// "+f.getName()+" @"+f.getEntryPoint()+" ////////");
      DecompileResults dr=di.decompileFunction(f,120,monitor);
      if(dr!=null&&dr.getDecompiledFunction()!=null) println(dr.getDecompiledFunction().getC());
    }
  }
}
