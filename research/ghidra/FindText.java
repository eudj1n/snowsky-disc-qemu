// Read-only string/reference lookup. Args: case-insensitive Java regexes.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.util.regex.Pattern;

public class FindText extends GhidraScript {
  public void run() throws Exception {
    Pattern[] patterns = new Pattern[getScriptArgs().length];
    for (int i = 0; i < patterns.length; i++)
      patterns[i] = Pattern.compile(getScriptArgs()[i], Pattern.CASE_INSENSITIVE);
    DataIterator items = currentProgram.getListing().getDefinedData(true);
    while (items.hasNext() && !monitor.isCancelled()) {
      Data item = items.next();
      Object value = item.getValue();
      if (!(value instanceof String)) continue;
      for (Pattern pattern : patterns) {
        if (!pattern.matcher((String)value).find()) continue;
        println(item.getAddress() + " " + value);
        ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(item.getAddress());
        while (refs.hasNext()) {
          Reference ref = refs.next();
          Function function = getFunctionContaining(ref.getFromAddress());
          println("  " + ref.getFromAddress() + " " +
                  (function == null ? "data" : function.getEntryPoint().toString()));
        }
        break;
      }
    }
  }
}
