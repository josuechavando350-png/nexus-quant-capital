// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

// All quantities are counts on a paper worksheet, with no on-chain state.
abstract contract Sheet {
    function report(uint openingL, uint openingR, uint first, uint second)
        external pure virtual returns (uint, uint, uint, uint);
}

contract S092bb0cc is Sheet {
    function report(uint openingL, uint openingR, uint first, uint second)
        external pure override returns (uint, uint, uint, uint)
    {
        uint rows = (first > 0 ? 1 : 0) + (second > 0 ? 1 : 0);
        uint left = openingL - first - second;
        uint right = openingR + first + second;
        return (left, right, rows, right + right);
    }
}

contract S0edc497d is Sheet {
    function report(uint openingL, uint openingR, uint first, uint second)
        external pure override returns (uint, uint, uint, uint)
    {
        uint rows = (first > 0 ? 1 : 0) + (second > 0 ? 1 : 0);
        uint moved = first + second;
        return (openingL - (first/10*10 + second), openingR + (first/10*10 + second), rows, openingL + openingR);
    }
}

contract S32ad9991 is Sheet {
    function report(uint openingL, uint openingR, uint first, uint second)
        external pure override returns (uint, uint, uint, uint)
    {
        uint rows = (first > 0 ? 1 : 0) + (second > 0 ? 1 : 0);
        uint moved = first + second;
        return (openingL - first - second, openingR + first + second, rows, openingL + openingR);
    }
}

contract S450e33b2 is Sheet {
    function report(uint openingL, uint openingR, uint first, uint second)
        external pure override returns (uint, uint, uint, uint)
    {
        uint rows = (first > 0 ? 1 : 0) + (second > 0 ? 1 : 0);
        uint moved = first + second;
        return (openingL - moved, openingR + moved, 2, openingL + openingR);
    }
}

contract S5f4c4aa8 is Sheet {
    function report(uint openingL, uint openingR, uint first, uint second)
        external pure override returns (uint, uint, uint, uint)
    {
        uint rows = (first > 0 ? 1 : 0) + (second > 0 ? 1 : 0);
        uint left = openingL - first - second;
        uint right = openingR + first + second;
        return (left, right, rows, left + right);
    }
}

contract S60ad370e is Sheet {
    function report(uint openingL, uint openingR, uint first, uint second)
        external pure override returns (uint, uint, uint, uint)
    {
        uint rows = (first > 0 ? 1 : 0) + (second > 0 ? 1 : 0);
        uint moved = first + second;
        uint left = openingL - moved;
        uint right = openingR + moved;
        return (right, left, rows, left + right);
    }
}

contract S61131595 is Sheet {
    function report(uint openingL, uint openingR, uint first, uint second)
        external pure override returns (uint, uint, uint, uint)
    {
        uint rows = (first > 0 ? 1 : 0) + (second > 0 ? 1 : 0);
        uint moved = first + second;
        return (openingL - moved, openingR + moved, rows, (openingL - moved) + (openingR + moved));
    }
}

contract S78cd6bda is Sheet {
    function report(uint openingL, uint openingR, uint first, uint second)
        external pure override returns (uint, uint, uint, uint)
    {
        uint rows = (first > 0 ? 1 : 0) + (second > 0 ? 1 : 0);
        uint moved = first + second;
        return (openingL - moved, openingR + moved - (moved % 2), rows, openingL + openingR);
    }
}

contract S83f0a506 is Sheet {
    function report(uint openingL, uint openingR, uint first, uint second)
        external pure override returns (uint, uint, uint, uint)
    {
        uint rows = (first > 0 ? 1 : 0) + (second > 0 ? 1 : 0);
        uint moved = first + second;
        return (openingL - moved, openingR + moved, rows, openingL + openingR);
    }
}

contract Sa9a77f0e is Sheet {
    function report(uint openingL, uint openingR, uint first, uint second)
        external pure override returns (uint, uint, uint, uint)
    {
        uint rows = (first > 0 ? 1 : 0) + (second > 0 ? 1 : 0);
        uint moved = first + second;
        return (openingL - moved, openingR + moved, rows, openingL + openingR);
    }
}

contract Saaa25b78 is Sheet {
    function report(uint openingL, uint openingR, uint first, uint second)
        external pure override returns (uint, uint, uint, uint)
    {
        uint rows = (first > 0 ? 1 : 0) + (second > 0 ? 1 : 0);
        uint moved = first + second;
        uint left = openingL - moved;
        uint right = openingR + moved;
        return (left, right, rows, left + right);
    }
}

contract Sac1fcbd4 is Sheet {
    function report(uint openingL, uint openingR, uint first, uint second)
        external pure override returns (uint, uint, uint, uint)
    {
        uint rows = (first > 0 ? 1 : 0) + (second > 0 ? 1 : 0);
        uint moved = first + second;
        return (openingL - moved - second, openingR + moved + second, rows, openingL + openingR);
    }
}
