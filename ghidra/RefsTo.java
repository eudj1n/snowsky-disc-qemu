import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
public class RefsTo extends GhidraScript {
  public void run() throws Exception {
    for (String a : getScriptArgs()) {
      Address t = currentProgram.getAddressFactory().getAddress(a);
      println("==== refs to " + a + " ====");
      ReferenceIterator it = currentProgram.getReferenceManager().getReferencesTo(t);
      while (it.hasNext()) {
        Reference r = it.next();
        Address from = r.getFromAddress();
        Function f = getFunctionContaining(from);
        println(r.getReferenceType() + " from " + from + (f!=null? "  in "+f.getName()+" @"+f.getEntryPoint() : ""));
      }
    }
  }
}
