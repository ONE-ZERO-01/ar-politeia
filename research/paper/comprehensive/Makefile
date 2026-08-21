# AR-Politeia Cycle 1 -- Comprehensive record build
# PDFs are Git-ignored. Run `make` to produce main.pdf and supplementary PDF.

LATEXMK := latexmk
PDFLATEX := -pdf -interaction=nonstopmode -halt-on-error

.PHONY: all main supplementary clean

all: main.pdf supplementary/supplementary.pdf

main.pdf: main.tex
	$(LATEXMK) $(PDFLATEX) main.tex

supplementary/supplementary.pdf: supplementary/supplementary.tex
	cd supplementary && $(LATEXMK) $(PDFLATEX) supplementary.tex

clean:
	$(LATEXMK) -C main.tex || true
	cd supplementary && $(LATEXMK) -C supplementary.tex || true
	rm -f main.pdf supplementary/supplementary.pdf
