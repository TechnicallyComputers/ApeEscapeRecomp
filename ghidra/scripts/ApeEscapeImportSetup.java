// Establish the PS-EXE context that Raw Binary import cannot infer.
//@category PSXRecomp

import java.math.BigInteger;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.lang.Register;

public class ApeEscapeImportSetup extends GhidraScript {
    private static final long ENTRY_POINT = 0x800A3660L;
    private static final String INITIAL_GP = "800BCC60";

    @Override
    public void run() throws Exception {
        Address entry = toAddr(ENTRY_POINT);
        Register gp = currentProgram.getRegister("gp");
        if (gp == null) {
            throw new IllegalStateException("MIPS gp register is unavailable");
        }

        currentProgram.getProgramContext().setValue(
            gp,
            currentProgram.getMinAddress(),
            currentProgram.getMaxAddress(),
            new BigInteger(INITIAL_GP, 16));

        disassemble(entry);
        if (getFunctionAt(entry) == null) {
            createFunction(entry, "entry");
        }
        currentProgram.getSymbolTable().addExternalEntryPoint(entry);
    }
}
