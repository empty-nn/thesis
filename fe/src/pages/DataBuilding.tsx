import { useDataPipeline } from "@/hooks/useDataPipeline";
import DataBuildingWindow from "../components/data-building/DataBuildingWindow";
import DataSideBar from "../components/data-building/DataSideBar";
import { dataBuildingSteps } from "@/components/data-building/types";

function DataBuilding() {
  const pipeline = useDataPipeline();

  return (
    <div className="flex">
      <DataSideBar
        steps={dataBuildingSteps}
        activeStepId={pipeline.state.activeStepId}
        stepStatuses={pipeline.state.stepStatuses}
        sourceType={pipeline.state.sourceType}
        htmlUrl={pipeline.state.htmlUrl}
        selectedFile={pipeline.state.selectedFile}
        hasDataSource={pipeline.state.hasDataSource}
        canRunStep={pipeline.actions.canRunStep}
        onSelectStep={pipeline.actions.setActiveStepId}
        onRunStep={pipeline.actions.handleRunStep}
        onStopStep={pipeline.actions.handleStopStep}
        onResetPipeline={pipeline.actions.resetPipelineState}
        onSourceTypeChange={pipeline.actions.handleSourceTypeChange}
        onUrlChange={pipeline.actions.handleUrlChange}
        onFileChange={pipeline.actions.handleFileChange}
      />

      <DataBuildingWindow
        activeStep={pipeline.state.activeStep}
        activeStepStatus={pipeline.state.stepStatuses[pipeline.state.activeStep.id]}
        sourceType={pipeline.state.sourceType}
        stepResults={pipeline.state.stepResults}
        stepOptions={pipeline.state.stepOptions}
        onHandleSaveResult={pipeline.actions.handleSaveResult}
        onUpdateStepResult={pipeline.actions.handleUpdateStepResult}
        onUpdateStepOption={(optionId, value) =>
          pipeline.actions.handleUpdateStepOption(
            pipeline.state.activeStep.id,
            optionId,
            value
          )
        }
      />
    </div>
  );
}

export default DataBuilding;