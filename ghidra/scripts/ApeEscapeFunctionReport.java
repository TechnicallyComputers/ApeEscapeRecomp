// Emit decompilation and call-graph context for selected Ape Escape addresses.
//@category PSXRecomp

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class ApeEscapeFunctionReport extends GhidraScript {
    private static String describe(Function function) {
        return String.format(
            "%s @ %s (%d bytes)",
            function.getName(),
            function.getEntryPoint(),
            function.getBody().getNumAddresses());
    }

    private static List<Function> sorted(Set<Function> functions) {
        List<Function> result = new ArrayList<>(functions);
        result.sort(Comparator.comparing(Function::getEntryPoint));
        return result;
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            throw new IllegalArgumentException(
                "usage: ApeEscapeFunctionReport.java <output.txt> <address>...");
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.toggleCCode(true);
        decompiler.toggleSyntaxTree(true);
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("Decompiler could not open the program");
        }

        try (PrintWriter out = new PrintWriter(new FileWriter(args[0], false))) {
            out.printf("Program: %s%n", currentProgram.getName());
            out.printf("Image base: %s%n%n", currentProgram.getImageBase());

            for (int i = 1; i < args.length; i++) {
                Address address = toAddr(args[i]);
                Function function =
                    currentProgram.getFunctionManager().getFunctionContaining(address);
                out.printf("===== QUERY %s =====%n", address);
                if (function == null) {
                    out.println("No containing function");
                    out.println();
                    continue;
                }

                out.println(describe(function));
                out.printf("Signature: %s%n", function.getSignature());

                out.println("Callers:");
                for (Function caller : sorted(function.getCallingFunctions(monitor))) {
                    out.printf("  %s%n", describe(caller));
                }

                out.println("Callees:");
                for (Function callee : sorted(function.getCalledFunctions(monitor))) {
                    out.printf("  %s%n", describe(callee));
                }

                DecompileResults results =
                    decompiler.decompileFunction(function, 120, monitor);
                out.printf("Decompile completed: %s%n", results.decompileCompleted());
                if (results.decompileCompleted() && results.getDecompiledFunction() != null) {
                    out.println(results.getDecompiledFunction().getC());
                }
                else {
                    out.printf("Decompiler error: %s%n", results.getErrorMessage());
                }
                out.println();
            }
        }
        finally {
            decompiler.dispose();
        }
    }
}
