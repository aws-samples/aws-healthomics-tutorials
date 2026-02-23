// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

trait ImportJobParameters {
  def jobName: String
  def databaseName: String
  def tableName: String
  def tablePath: String
  def tableFormat: TableFormat.Value
  def jobId: String
  def inputPath: String
  def referenceArn: String
  def runLeftNormalization: Boolean
  def glueArgs: Array[String]
  def catalog: String = "job_catalog"
  def tableLocation: String = List(catalog, databaseName, tableName).mkString(".")
  def referenceStoreItem: Option[ReferenceStoreItem]
  def s3aPath: String = inputPath.replace("s3://", "s3a://")
  def annotationFields: AnnotationFields
  def supportsVEPParsing: Boolean = TableFormat.supportsVEPParsing(tableFormat.id)
  def tableSortKeys: List[String]
}
