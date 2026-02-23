// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.common

import com.amazon.vincent.job.models.ReferenceStoreItem
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.mockito.ArgumentMatchers.any
import org.mockito.Mockito._
import org.scalatest.funsuite.AnyFunSuite
import org.scalatest.{BeforeAndAfterAll, BeforeAndAfterEach}
import org.scalatestplus.junit.JUnitRunner
import software.amazon.awssdk.core.ResponseBytes
import software.amazon.awssdk.services.omics.OmicsClient
import software.amazon.awssdk.services.omics.model._

import java.nio.file.{Files, Paths}

@RunWith(classOf[JUnitRunner])
class ReferenceStoreDaoTest extends AnyFunSuite with BeforeAndAfterEach with BeforeAndAfterAll {

  private var mockOmicsClient: OmicsClient = _
  private var referenceStoreDao: ReferenceStoreDao = _
  private var temporaryFolder: TemporaryFolder = _
  private val referenceId = "123456789"
  private val referenceStoreId = "987654321"
  private val customerId = "999999999"
  private val totalParts = 2
  private val mockReferenceMetaDataResponse = generateReferenceMetaDataResponse()
  private val referenceArn =
    s"""arn:aws:omics:us-west-2:$customerId:
      |referenceStore/$referenceStoreId/
      |reference/$referenceId
      |""".stripMargin.replaceAll("\n", "")

  private val referenceStoreItem = ReferenceStoreItem(referenceArn)

  private val getReferenceMetadataRequest = GetReferenceMetadataRequest
    .builder()
    .referenceStoreId(referenceStoreId)
    .id(referenceId)
    .build()

  def generateReferenceMetaDataResponse(): GetReferenceMetadataResponse = {
    val fileInformation = FileInformation
      .builder()
      .partSize(1000)
      .totalParts(totalParts)
      .build()
    GetReferenceMetadataResponse
      .builder()
      .referenceStoreId(referenceStoreId)
      .files(ReferenceFiles.builder().source(fileInformation).build())
      .build()
  }

  override def beforeAll(): Unit = {
    temporaryFolder = new TemporaryFolder()
    temporaryFolder.create()
    super.beforeAll()
  }

  override def beforeEach(): Unit = {
    mockOmicsClient = mock(classOf[OmicsClient])
    referenceStoreDao = ReferenceStoreDao(mockOmicsClient)
    super.beforeEach()
  }

  override def afterAll(): Unit = {
    temporaryFolder.delete()
    super.afterAll()
  }

  test("Get Reference Parts") {
    when(mockOmicsClient.getReferenceMetadata(getReferenceMetadataRequest))
      .thenReturn(mockReferenceMetaDataResponse)

    val partsNumber = referenceStoreDao.getReferencePartsCount(referenceStoreItem)
    assert(partsNumber === totalParts)
  }

  test("Get Reference") {
    when(mockOmicsClient.getReferenceMetadata(getReferenceMetadataRequest))
      .thenReturn(mockReferenceMetaDataResponse)

    val responseByte =
      ResponseBytes.fromByteArray(GetReferenceResponse.builder.build(), "content".getBytes())
    when(mockOmicsClient.getReferenceAsBytes(any(classOf[GetReferenceRequest])))
      .thenReturn(responseByte)

    val tempPath = temporaryFolder.newFile().getAbsolutePath

    referenceStoreDao.downloadReference(referenceStoreItem, tempPath)

    // there are 2 parts so content get written twice
    assert(Files.readAllBytes(Paths.get(tempPath)) === "contentcontent".getBytes())
  }
}
