# ── MBA6223 Finance Dashboard — Infrastructure Makefile ───────────────────────
#
# Usage:
#   make layer      Build the Lambda Layer (downloads deps + copies src/)
#   make synth      Synthesise CloudFormation templates
#   make deploy     Deploy all stacks to AWS
#   make destroy    Tear down all stacks (prompts for confirmation)
#   make diff       Show pending changes vs deployed stacks

PYTHON        := python3.11
LAYER_OUT     := lambda/layer/python/lib/python3.11/site-packages
LAYER_REQS    := lambda/layer/requirements.txt
SRC_DIR       := ../src

.PHONY: install layer synth deploy diff destroy clean

install:
	pip install -r requirements.txt

layer:
	@echo "→ Installing layer dependencies (ARM64 manylinux wheels)..."
	pip install \
		-r $(LAYER_REQS) \
		-t $(LAYER_OUT) \
		--platform manylinux2014_aarch64 \
		--only-binary=:all: \
		--upgrade
	@echo "→ Copying src/ package into layer..."
	cp -r $(SRC_DIR) $(LAYER_OUT)/src
	@echo "✓ Layer ready at $(LAYER_OUT)"

synth: layer
	cdk synth

deploy: layer
	cdk deploy --all --require-approval broadening

diff:
	cdk diff --all

destroy:
	cdk destroy --all

clean:
	rm -rf $(LAYER_OUT) cdk.out
