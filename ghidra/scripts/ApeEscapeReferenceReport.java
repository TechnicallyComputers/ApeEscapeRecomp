// Emit references to selected Ape Escape addresses, grouped by containing function.
//@category PSXRecomp

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApeEscapeReferenceReport extends GhidraScript {
    private static final class ReferenceRow {
        Address from;
        String type;
        String function;

        ReferenceRow(Address from, String type, String function) {
            this.from = from;
            this.type = type;
            this.function = function;
        }
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            throw new IllegalArgumentException(
                "usage: ApeEscapeReferenceReport.java <output.txt> <address>...");
        }

        try (PrintWriter out = new PrintWriter(new FileWriter(args[0], false))) {
            out.printf("Program: %s%n", currentProgram.getName());
            out.printf("Image base: %s%n%n", currentProgram.getImageBase());

            for (int i = 1; i < args.length; i++) {
                Address target = toAddr(args[i]);
                List<ReferenceRow> rows = new ArrayList<>();
                ReferenceIterator references =
                    currentProgram.getReferenceManager().getReferencesTo(target);
                while (references.hasNext()) {
                    Reference reference = references.next();
                    Address from = reference.getFromAddress();
                    Function function =
                        currentProgram.getFunctionManager().getFunctionContaining(from);
                    rows.add(new ReferenceRow(
                        from,
                        reference.getReferenceType().toString(),
                        function == null
                            ? "<no function>"
                            : function.getName() + " @ " + function.getEntryPoint()));
                }

                rows.sort(Comparator.comparing(row -> row.from));
                out.printf("===== REFERENCES TO %s (%d) =====%n", target, rows.size());
                for (ReferenceRow row : rows) {
                    out.printf("%s  %-18s  %s%n", row.from, row.type, row.function);
                }
                out.println();
            }
        }
    }
}
